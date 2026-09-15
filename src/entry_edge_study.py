#!/usr/bin/env python3
"""Issue #2 stage 1: fixed Entry Edge candidates versus 0050."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

START, END = pd.Timestamp("2021-01-04"), pd.Timestamp("2026-08-11")
HORIZONS = (5, 10, 20)
COST = 0.004798
BENCHMARK = "0050"
EXCLUDED = {"ETF", "ETN", "上櫃ETF", "上櫃指數股票型基金(ETF)", "受益證券", "存託憑證", "指數投資證券(ETN)"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--prices", default="data/processed/prices.parquet")
    p.add_argument("--stock-info", default="data/processed/stock_info.parquet")
    p.add_argument("--out", default="output/entry_edge")
    return p.parse_args()


def load_prices(prices: str, stock_info: str) -> pd.DataFrame:
    missing_files = [x for x in (prices, stock_info) if not Path(x).exists()]
    if missing_files:
        raise SystemExit("data gate blocked; restore: " + ", ".join(missing_files))
    p = pd.read_parquet(prices)
    required = {"stock_id", "date", "open", "high", "low", "close", "limit_up"}
    missing = required - set(p.columns)
    if missing:
        raise ValueError(f"prices missing official-data fields: {sorted(missing)}")
    p = p.copy()
    p.stock_id = p.stock_id.astype(str).str.zfill(4)
    p.date = pd.to_datetime(p.date)
    if p.duplicated(["stock_id", "date"]).any():
        raise ValueError("duplicate (stock_id,date) keys")
    info = pd.read_parquet(stock_info)
    if not {"stock_id", "industry_category"}.issubset(info.columns):
        raise ValueError("stock_info missing stock_id/industry_category")
    excluded = set(info.loc[info.industry_category.isin(EXCLUDED), "stock_id"].astype(str).str.zfill(4))
    keep = (~p.stock_id.isin(excluded)) | (p.stock_id == BENCHMARK)
    p = p.loc[keep].sort_values(["stock_id", "date"]).reset_index(drop=True)
    p = p[(p.date >= START) & (p.date <= END)].copy()
    if BENCHMARK not in set(p.stock_id):
        raise ValueError("0050 benchmark rows are required")
    cents = lambda s: np.rint(pd.to_numeric(s) * 100).astype("Int64")
    p["locked"] = cents(p.close).eq(cents(p.limit_up))
    g = p.groupby("stock_id", sort=False)
    p["within_pos"] = g.cumcount()
    p["group_size"] = g.stock_id.transform("size")
    p["prior10_locked"] = g.locked.transform(lambda s: s.shift().rolling(10, min_periods=1).sum()).fillna(0)
    return p


def episode_mask(stock: np.ndarray, pos: np.ndarray, gap: int = 20) -> np.ndarray:
    keep = np.zeros(len(stock), dtype=bool)
    last_stock, last_pos = None, -10_000
    for i, (sid, at) in enumerate(zip(stock, pos)):
        if sid != last_stock or at - last_pos > gap:
            keep[i] = True
            last_stock, last_pos = sid, at
    return keep


def build_events(p: pd.DataFrame) -> pd.DataFrame:
    q = p[(p.stock_id != BENCHMARK) & p.locked].copy()
    q["near_limit"] = q.low >= q.limit_up * .99
    q["hist2"] = q.prior10_locked >= 2
    specs = {"A_NEAR_LIMIT": q.near_limit, "B_HIST2": q.hist2,
             "C_NEAR_LIMIT_HIST2": q.near_limit & q.hist2}
    benchmark = p[p.stock_id == BENCHMARK].set_index("date")
    rows = []
    for signal, mask in specs.items():
        z = q.loc[mask].copy()
        for dataset, selected in (("Raw", np.ones(len(z), bool)),
                                  ("Episode", episode_mask(z.stock_id.to_numpy(), z.within_pos.to_numpy()))):
            for x in z.loc[selected].itertuples(index=False):
                path = p[(p.stock_id == x.stock_id) & (p.within_pos >= x.within_pos)].head(max(HORIZONS) + 2)
                if len(path) <= max(HORIZONS):
                    continue
                entry = path.iloc[1]
                if entry.date not in benchmark.index:
                    continue
                b0 = benchmark.loc[entry.date]
                if isinstance(b0, pd.DataFrame): b0 = b0.iloc[0]
                for h in HORIZONS:
                    stock_exit = path.iloc[h]
                    if stock_exit.date not in benchmark.index:
                        continue
                    bh = benchmark.loc[stock_exit.date]
                    if isinstance(bh, pd.DataFrame): bh = bh.iloc[0]
                    stock_ret = stock_exit.close / entry.open - 1 - COST
                    bench_ret = bh.close / b0.open - 1
                    rows.append({"stock_id": x.stock_id, "signal_date": x.date,
                                 "entry_date": entry.date, "exit_date": stock_exit.date,
                                 "year": x.date.year, "signal": signal, "dataset": dataset,
                                 "horizon": h, "stock_return": stock_ret,
                                 "benchmark_return": bench_ret, "excess_return": stock_ret - bench_ret})
    return pd.DataFrame(rows)


def metrics(g: pd.DataFrame) -> pd.Series:
    r, e = g.stock_return, g.excess_return
    return pd.Series({"N": len(g), "mean_return": r.mean(), "median_return": r.median(),
                      "mean_excess": e.mean(), "median_excess": e.median(),
                      "win_rate": (r > 0).mean(), "beat_0050": (e > 0).mean(),
                      "p_plus10": (r >= .10).mean(), "p_plus20": (r >= .20).mean(),
                      "p_loss10": (r <= -.10).mean()})


def summarize(events: pd.DataFrame, yearly: bool = False) -> pd.DataFrame:
    keys = (["year"] if yearly else []) + ["signal", "dataset", "horizon"]
    return events.groupby(keys, sort=False).apply(metrics, include_groups=False).reset_index()


def main() -> None:
    a = parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    p = load_prices(a.prices, a.stock_info)
    events = build_events(p)
    if events.empty:
        raise ValueError("no complete eligible events")
    summary, yearly = summarize(events), summarize(events, yearly=True)
    events.to_parquet(out / "events.parquet", index=False)
    summary.to_csv(out / "summary.csv", index=False)
    yearly.to_csv(out / "yearly.csv", index=False)
    audit = {"date_min": str(p.date.min().date()), "date_max": str(p.date.max().date()),
             "benchmark": BENCHMARK, "cost": COST, "horizons": HORIZONS,
             "signals": ["A_NEAR_LIMIT", "B_HIST2", "C_NEAR_LIMIT_HIST2"],
             "event_rows": len(events)}
    (out / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    main()
