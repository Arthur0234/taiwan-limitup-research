import numpy as np
import pandas as pd

from src.ma20_exit_backtest import RULES, below_runs, first_true, simulate, summarize


def test_below_run_and_first_true_include_t0_history():
    below = np.array([[False, True, True, True, False]])
    runs = below_runs(below)
    assert runs.tolist() == [[0, 1, 2, 3, 0]]
    assert first_true(runs >= 2, end=4).item() == 2


def test_close_signal_executes_next_open_and_no_exit_uses_t20_close():
    n = 31
    close = np.full((1, n), 100.0)
    close[0, 1] = 94.0
    open_ = np.full((1, n), 100.0)
    open_[0, 2] = 93.0
    dates = np.array(pd.date_range("2024-01-01", periods=n), dtype="datetime64[ns]")[None, :]
    path = {
        "open": open_, "high": np.full((1, n), 101.0), "low": np.full((1, n), 92.0),
        "close": close, "ma20": np.full((1, n), 95.0), "date": dates,
    }
    entries = pd.DataFrame({
        "stock_id": ["1101"], "entry_date": pd.to_datetime(["2024-01-01"]),
        "regime": ["LIMIT_UP"], "variant": ["A1_ALL_LOCKED"],
    })
    trades = simulate(entries, path).set_index("rule")
    assert set(trades.index) == set(RULES)
    assert trades.loc["STOP_5", "trigger_age"] == 1
    assert trades.loc["STOP_5", "exit_age"] == 2
    assert trades.loc["STOP_5", "exit_price"] == 93.0
    assert trades.loc["NO_EARLY_EXIT", "exit_age"] == 20
    assert trades.loc["NO_EARLY_EXIT", "exit_price"] == 100.0


def test_summary_keeps_variants_separate():
    rows = []
    for variant in ["A1_ALL_LOCKED", "A2_HIST2_LOCKED"]:
        rows.append({
            "year": 2024, "regime": "LIMIT_UP", "variant": variant, "rule": "STOP_5",
            "net_return": .1, "no_exit_return": .2, "exit_age": 5,
            "early_exit": True, "trade_max_drawdown": -.05, "false_exit_10d": False,
            "recovery_above_peak_5d": False, "recovery_above_peak_10d": False,
        })
    out = summarize(pd.DataFrame(rows))
    assert len(out) == 2
    assert set(out.variant) == {"A1_ALL_LOCKED", "A2_HIST2_LOCKED"}
