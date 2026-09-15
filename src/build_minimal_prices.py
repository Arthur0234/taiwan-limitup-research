#!/usr/bin/env python3
"""Build the minimal price parquet required by ma20_exit_backtest.

This intentionally does NOT recreate the legacy limit-up research dataset.
Canonical output schema: stock_id,date,open,high,low,close.

Provider adapters should emit that schema. Keep source acquisition separate so
we can swap TWSE/TPEx official downloads without changing the backtest.
"""
from pathlib import Path
import argparse
import pandas as pd

COLS=["stock_id","date","open","high","low","close"]

def args():
    p=argparse.ArgumentParser()
    p.add_argument("--twse", help="normalized TWSE CSV/parquet")
    p.add_argument("--tpex", help="normalized TPEx CSV/parquet")
    p.add_argument("--out", default="data/processed/prices.parquet")
    return p.parse_args()

def load(path):
    x=pd.read_parquet(path) if str(path).endswith(".parquet") else pd.read_csv(path,dtype={"stock_id":str})
    miss=set(COLS)-set(x.columns)
    if miss: raise ValueError(f"{path} missing {sorted(miss)}")
    x=x[COLS].copy(); x.stock_id=x.stock_id.astype(str); x.date=pd.to_datetime(x.date)
    for c in ["open","high","low","close"]: x[c]=pd.to_numeric(x[c],errors="coerce")
    return x.dropna(subset=COLS).drop_duplicates(["stock_id","date"])

def main():
    a=args(); paths=[x for x in (a.twse,a.tpex) if x]
    if not paths: raise SystemExit("provide --twse and/or --tpex normalized source")
    x=pd.concat([load(q) for q in paths],ignore_index=True).sort_values(["stock_id","date"])
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True); x.to_parquet(out,index=False)
    print({"rows":len(x),"stocks":x.stock_id.nunique(),"min":str(x.date.min().date()),"max":str(x.date.max().date())})

if __name__=="__main__": main()
