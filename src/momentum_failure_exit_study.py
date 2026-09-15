#!/usr/bin/env python3
"""Recovered momentum failure/exit research contract.

Do not run new strategy studies until processed inputs are restored and audited.
Canonical full source and prior outputs remain preserved in ChatGPT Library.
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
START, END = "2021-01-04", "2026-08-11"
OBS, FUTURE = 20, 10
COST = 0.004798
DD_LEVELS = [0.03, 0.05, 0.08, 0.10]
MA_WINDOWS = [5, 10, 20]
TIME_LEVELS = [3, 5, 10]

if __name__ == "__main__":
    raise SystemExit("Recovery guard: restore and audit data/processed inputs first.")
