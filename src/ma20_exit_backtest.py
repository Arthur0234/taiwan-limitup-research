#!/usr/bin/env python3
"""Minimal MA20 exit-rule comparison.

Input prices parquet: stock_id,date,open,high,low,close.
Input entries CSV: stock_id,entry_date[,entry_price].
Signals are evaluated at close and executed next trading-day open.
"""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd

COST = 0.004798
RULES = ("BASE", "MA20_1", "MA20_2", "MA20_3", "STOP_5", "STOP_7")


def args():
    p = argparse.ArgumentParser()
    p.add_argument("--prices", default="data/processed/prices.parquet")
    p.add_argument("--entries", required=True)
    p.add_argument("--out", default="output/ma20_exit")
    p.add_argument("--max-hold", type=int, default=60)
    return p.parse_args()


def summarize(t):
    def one(g):
        r = g.net_return
        return pd.Series({
            "N": len(g), "mean_return": r.mean(), "median_return": r.median(),
            "win_rate": (r > 0).mean(), "avg_loss": r[r < 0].mean(),
            "avg_holding_days": g.holding_days.mean(),
            "false_exit_5d": (g.post5 > 0).mean(),
            "post_exit_5d": g.post5.mean(), "post_exit_10d": g.post10.mean(),
            "post_exit_20d": g.post20.mean(),
        })
    return t.groupby("rule", sort=False).apply(one, include_groups=False).reset_index()


def main():
    a = args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    p = pd.read_parquet(a.prices)
    need = {"stock_id","date","open","high","low","close"}
    miss = need - set(p.columns)
    if miss: raise ValueError(f"prices missing: {sorted(miss)}")
    p = p[list(need)].copy(); p.stock_id = p.stock_id.astype(str); p.date = pd.to_datetime(p.date)
    p = p.sort_values(["stock_id","date"]).reset_index(drop=True)
    g = p.groupby("stock_id", sort=False)
    p["ma20"] = g.close.transform(lambda s: s.rolling(20, min_periods=20).mean())
    p["below"] = p.close < p.ma20
    p["below_run"] = p.groupby("stock_id").below.transform(lambda s: s.groupby((s != s.shift()).cumsum()).cumcount()+1) * p.below

    e = pd.read_csv(a.entries, dtype={"stock_id":str}); e.entry_date = pd.to_datetime(e.entry_date)
    rows=[]
    for x in e.itertuples(index=False):
        z = p[(p.stock_id==x.stock_id) & (p.date>=x.entry_date)].head(a.max_hold+22).reset_index(drop=True)
        if len(z)<2: continue
        ep = getattr(x,"entry_price",np.nan)
        if pd.isna(ep): ep=float(z.iloc[0].open)
        for rule in RULES:
            sig=None
            if rule.startswith("MA20_"):
                n=int(rule[-1]); q=np.flatnonzero(z.below_run.to_numpy()>=n); sig=int(q[0]) if len(q) else None
            elif rule.startswith("STOP_"):
                stop=-int(rule.split("_")[1])/100
                q=np.flatnonzero(z.close.to_numpy()/ep-1 <= stop); sig=int(q[0]) if len(q) else None
            if rule=="BASE" or sig is None: exit_i=min(a.max_hold, len(z)-1); exit_px=float(z.iloc[exit_i].close)
            else: exit_i=min(sig+1, len(z)-1); exit_px=float(z.iloc[exit_i].open)
            ret=exit_px/ep-1-COST
            rec={"stock_id":x.stock_id,"entry_date":x.entry_date,"rule":rule,"entry_price":ep,
                 "exit_date":z.iloc[exit_i].date,"exit_price":exit_px,"holding_days":exit_i,"net_return":ret}
            for h in (5,10,20):
                j=exit_i+h; rec[f"post{h}"]=(float(z.iloc[j].close)/exit_px-1) if j<len(z) else np.nan
            rows.append(rec)
    t=pd.DataFrame(rows); t.to_csv(out/"trades.csv",index=False)
    summarize(t).to_csv(out/"summary.csv",index=False)

if __name__ == "__main__": main()
