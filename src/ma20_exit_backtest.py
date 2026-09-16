#!/usr/bin/env python3
"""Preregistered MA20 persistence versus fixed-stop exit study.

The frozen cohort enters at T0 close. Exit signals are close-confirmed during
T+1..T+19 and execute at the next stock trading-day open. Positions without an
early signal exit at T+20 close. All returns include the preserved 0.4798%
round-trip cost convention.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


COST = 0.004798
OBS = 20
RECOVERY = 10
RULES = ("NO_EARLY_EXIT", "MA20_1D", "MA20_2D", "MA20_3D", "STOP_5", "STOP_7")
EXPECTED_COHORTS = {
    ("LIMIT_UP", "A1_ALL_LOCKED"): 28_930,
    ("LIMIT_UP", "A2_HIST2_LOCKED"): 9_142,
    ("LIMIT_UP", "A3_NEAR_LIMIT_LOCKED"): 1_751,
    ("NORMAL", "B_NORMAL_MOMENTUM"): 32_799,
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--prices", default="data/processed/prices.parquet")
    p.add_argument("--entries", default="research/issue_1_ma20/frozen_cohort_entries.csv")
    p.add_argument("--out", default="output/ma20_exit")
    p.add_argument("--data-end", default="2026-08-11")
    return p.parse_args()


def load_prices(path: str, data_end: str) -> pd.DataFrame:
    p = pd.read_parquet(path)
    required = {"stock_id", "date", "open", "high", "low", "close"}
    missing = required - set(p.columns)
    if missing:
        raise ValueError(f"prices missing: {sorted(missing)}")
    p = p[list(required)].copy()
    p["stock_id"] = p.stock_id.astype(str)
    p["date"] = pd.to_datetime(p.date)
    p = p[p.date <= pd.Timestamp(data_end)].sort_values(["stock_id", "date"]).reset_index(drop=True)
    if p.duplicated(["stock_id", "date"]).any():
        raise ValueError("duplicate (stock_id,date) keys")
    for c in ["open", "high", "low", "close"]:
        p[c] = pd.to_numeric(p[c], errors="coerce")
    if p[["open", "high", "low", "close"]].isna().any().any():
        raise ValueError("missing OHLC")
    g = p.groupby("stock_id", sort=False)
    p["ma20"] = g.close.transform(lambda s: s.rolling(20, min_periods=20).mean())
    p["within_pos"] = g.cumcount()
    p["group_size"] = g.stock_id.transform("size")
    return p


def load_entries(path: str) -> pd.DataFrame:
    e = pd.read_csv(path, dtype={"stock_id": str})
    required = {"stock_id", "entry_date", "regime", "variant"}
    missing = required - set(e.columns)
    if missing:
        raise ValueError(f"entries missing: {sorted(missing)}")
    e = e.copy()
    e["stock_id"] = e.stock_id.astype(str)
    e["entry_date"] = pd.to_datetime(e.entry_date)
    if e.duplicated(["variant", "stock_id", "entry_date"]).any():
        raise ValueError("duplicate cohort event keys")
    observed = e.groupby(["regime", "variant"]).size().to_dict()
    if observed != EXPECTED_COHORTS:
        raise ValueError(f"frozen cohort mismatch: {observed} != {EXPECTED_COHORTS}")
    return e.sort_values(["variant", "stock_id", "entry_date"]).reset_index(drop=True)


def extract_paths(
    p: pd.DataFrame, e: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, np.ndarray], pd.DataFrame]:
    keys = pd.MultiIndex.from_frame(p[["stock_id", "date"]])
    event_keys = pd.MultiIndex.from_arrays([e.stock_id, e.entry_date])
    event_idx = keys.get_indexer(event_keys)
    missing = e.loc[event_idx < 0].copy()
    e = e.loc[event_idx >= 0].reset_index(drop=True)
    event_idx = event_idx[event_idx >= 0]
    ages = np.arange(OBS + RECOVERY + 1)
    take = event_idx[:, None] + ages[None, :]
    if take.max() >= len(p):
        raise ValueError("cohort path exceeds price table")
    sid = p.stock_id.to_numpy()
    if not np.all(sid[take] == sid[event_idx][:, None]):
        raise ValueError("cohort lacks a complete T+30 same-stock path")
    path = {c: p[c].to_numpy()[take] for c in ["open", "high", "low", "close", "ma20", "date"]}
    return e, path, missing


def first_true(mask: np.ndarray, start: int = 1, end: int = OBS - 1) -> np.ndarray:
    z = mask[:, start : end + 1]
    hit = z.any(axis=1)
    return np.where(hit, z.argmax(axis=1) + start, np.nan)


def below_runs(below: np.ndarray) -> np.ndarray:
    runs = np.zeros_like(below, dtype=np.int16)
    runs[:, 0] = below[:, 0]
    for age in range(1, below.shape[1]):
        runs[:, age] = np.where(below[:, age], runs[:, age - 1] + 1, 0)
    return runs


def trigger_map(path: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    close = path["close"][:, :OBS]
    ma20 = path["ma20"][:, :OBS]
    runs = below_runs(np.isfinite(ma20) & (close < ma20))
    entry = path["close"][:, 0]
    return {
        "NO_EARLY_EXIT": np.full(len(entry), np.nan),
        "MA20_1D": first_true(runs >= 1),
        "MA20_2D": first_true(runs >= 2),
        "MA20_3D": first_true(runs >= 3),
        "STOP_5": first_true(close / entry[:, None] - 1 <= -0.05),
        "STOP_7": first_true(close / entry[:, None] - 1 <= -0.07),
    }


def future_max(values: np.ndarray, horizon: int) -> np.ndarray:
    out = np.full((len(values), OBS + 1), np.nan)
    for age in range(OBS + 1):
        end = min(age + horizon + 1, values.shape[1])
        if age + 1 < end:
            out[:, age] = values[:, age + 1 : end].max(axis=1)
    return out


def simulate(e: pd.DataFrame, path: dict[str, np.ndarray]) -> pd.DataFrame:
    entry = path["close"][:, 0]
    no_exit = path["close"][:, OBS] / entry - 1 - COST
    peak_close = np.maximum.accumulate(path["close"][:, : OBS + 1], axis=1)
    future_high10 = future_max(path["high"], 10)
    future_close5 = future_max(path["close"], 5)
    future_close10 = future_max(path["close"], 10)
    cum_low = np.minimum.accumulate(path["low"][:, 1 : OBS + 1], axis=1)
    idx = np.arange(len(e))
    rows = []
    for rule, trig in trigger_map(path).items():
        early = np.isfinite(trig) & (trig <= OBS - 1)
        trigger_age = np.where(early, trig, OBS).astype(int)
        exit_age = np.where(early, trigger_age + 1, OBS)
        exit_price = np.where(early, path["open"][idx, exit_age], path["close"][:, OBS])
        experienced_low = cum_low[idx, np.maximum(trigger_age - 1, 0)]
        experienced_low = np.where(early, np.minimum(experienced_low, exit_price), cum_low[:, -1])
        trigger_peak = peak_close[idx, trigger_age]
        false_exit = early & (future_high10[idx, exit_age] / exit_price - 1 >= 0.10)
        rec5 = early & (future_close5[idx, exit_age] > trigger_peak)
        rec10 = early & (future_close10[idx, exit_age] > trigger_peak)
        z = e[["stock_id", "entry_date", "regime", "variant"]].copy()
        z["year"] = z.entry_date.dt.year
        z["rule"] = rule
        z["entry_price"] = entry
        z["trigger_age"] = np.where(early, trigger_age, np.nan)
        z["exit_age"] = exit_age
        z["exit_date"] = path["date"][idx, exit_age]
        z["exit_price"] = exit_price
        z["net_return"] = exit_price / entry - 1 - COST
        z["no_exit_return"] = no_exit
        z["trade_max_drawdown"] = experienced_low / entry - 1
        z["early_exit"] = early
        z["false_exit_10d"] = false_exit
        z["recovery_above_peak_5d"] = rec5
        z["recovery_above_peak_10d"] = rec10
        z["ma20_ready_at_entry"] = np.isfinite(path["ma20"][:, 0])
        rows.append(z)
    return pd.concat(rows, ignore_index=True)


def metrics(g: pd.DataFrame) -> pd.Series:
    r = g.net_return.to_numpy()
    base = g.no_exit_return.to_numpy()
    early = g.early_exit.to_numpy(bool)
    winner10, winner20, winner30 = base >= .10, base >= .20, base >= .30
    denom = np.clip(base[winner10], 0, None).sum()
    return pd.Series({
        "N": len(g),
        "mean_return": np.mean(r), "median_return": np.median(r), "win_rate": np.mean(r > 0),
        "p_loss5": np.mean(r <= -.05), "p_loss10": np.mean(r <= -.10),
        "p_plus10": np.mean(r >= .10), "p_plus20": np.mean(r >= .20), "p_plus30": np.mean(r >= .30),
        "avg_holding_days": g.exit_age.mean(), "median_holding_days": g.exit_age.median(),
        "early_exit_rate": early.mean(),
        "winner10_retained": np.mean(r[winner10] >= .10) if winner10.any() else np.nan,
        "winner20_retained": np.mean(r[winner20] >= .20) if winner20.any() else np.nan,
        "winner30_retained": np.mean(r[winner30] >= .30) if winner30.any() else np.nan,
        "right_tail_capture": np.clip(r[winner10], 0, None).sum() / denom if denom else np.nan,
        "mean_trade_max_drawdown": g.trade_max_drawdown.mean(),
        "false_exit_10d": g.loc[g.early_exit, "false_exit_10d"].mean() if early.any() else np.nan,
        "recovery_above_peak_5d": g.loc[g.early_exit, "recovery_above_peak_5d"].mean() if early.any() else np.nan,
        "recovery_above_peak_10d": g.loc[g.early_exit, "recovery_above_peak_10d"].mean() if early.any() else np.nan,
    })


def summarize(trades: pd.DataFrame, yearly: bool = False) -> pd.DataFrame:
    keys = (["year"] if yearly else []) + ["regime", "variant", "rule"]
    return trades.groupby(keys, sort=False).apply(metrics, include_groups=False).reset_index()


def main() -> None:
    a = parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    prices = load_prices(a.prices, a.data_end)
    recovered_entries = load_entries(a.entries)
    entries, path, missing_entries = extract_paths(prices, recovered_entries)
    trades = simulate(entries, path)
    summary = summarize(trades)
    ready = summarize(trades[trades.ma20_ready_at_entry])
    yearly = summarize(trades, yearly=True)
    unique_events = trades.drop_duplicates(["variant", "stock_id", "entry_date"])
    audit = {
        "data_end": a.data_end,
        "price_date_min": str(prices.date.min().date()),
        "price_date_max": str(prices.date.max().date()),
        "price_rows": len(prices),
        "duplicate_price_keys": int(prices.duplicated(["stock_id", "date"]).sum()),
        "recovered_cohort_counts": {
            f"{k[0]}/{k[1]}": v
            for k, v in recovered_entries.groupby(["regime", "variant"]).size().items()
        },
        "analyzed_cohort_counts": {
            f"{k[0]}/{k[1]}": v
            for k, v in entries.groupby(["regime", "variant"]).size().items()
        },
        "excluded_legacy_events": len(missing_entries),
        "excluded_legacy_stock_ids": sorted(missing_entries.stock_id.unique().tolist()),
        "ma20_not_ready_at_entry": int((~unique_events.ma20_ready_at_entry).sum()),
        "rules": RULES,
        "cost": COST,
        "entry": "T0 close",
        "execution": "close-confirmed signal during T+1..T+19; next trading-day open; otherwise T+20 close",
    }
    trades.to_parquet(out / "trades.parquet", index=False)
    summary.to_csv(out / "summary.csv", index=False)
    ready.to_csv(out / "summary_ma20_ready.csv", index=False)
    yearly.to_csv(out / "yearly.csv", index=False)
    missing_entries.to_csv(out / "excluded_legacy_events.csv", index=False)
    (out / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
