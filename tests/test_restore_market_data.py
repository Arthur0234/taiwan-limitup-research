import pandas as pd
import pytest

from src.build_market_data import validate
from src.restore_market_data import audit_tick_rule, parse_finmind_prices, price_limits


def test_finmind_raw_prices_and_reference_price():
    data = parse_finmind_prices([{
        "date": "2026-09-01", "stock_id": "2330", "Trading_Volume": 10,
        "Trading_money": 100, "Trading_turnover": 2, "open": 2395,
        "max": 2440, "min": 2390, "close": 2440, "spread": 35,
    }], "twse")
    row = data.iloc[0]
    assert row.reference_price == 2405
    assert row.limit_up == 2645
    assert row.limit_down == 2165


def test_tick_boundaries_round_toward_reference():
    assert price_limits(9.99) == (10.95, 9.0)
    assert price_limits(100) == (110.0, 90.0)
    assert price_limits(1000) == (1100.0, 900.0)


def test_tpex_official_limits_validate_tick_rule():
    upper, lower = price_limits(100)
    frame = pd.DataFrame([{
        "next_reference_price": 100, "next_limit_up": upper, "next_limit_down": lower,
    }])
    result = audit_tick_rule(frame)
    assert result["exact_rate"] == 1


def test_tpex_audit_allows_rare_official_exceptions():
    rows = [{"next_reference_price": 100, "next_limit_up": 110, "next_limit_down": 90}] * 999
    rows.append({"next_reference_price": 100, "next_limit_up": 9995, "next_limit_down": 0.01})
    result = audit_tick_rule(pd.DataFrame(rows))
    assert result["exceptions"] == 1


def test_emerging_open_can_be_outside_range_but_is_not_valid_twse_ohlc():
    data = parse_finmind_prices([{
        "date": "2021-01-04", "stock_id": "2248", "Trading_Volume": 10,
        "Trading_money": 100, "Trading_turnover": 2, "open": 21.9,
        "max": 24.45, "min": 23.0, "close": 24.45, "spread": 1.45,
    }], "twse")
    assert data.iloc[0].open < data.iloc[0].low


def test_validation_rejects_missing_ohlc():
    prices = pd.DataFrame([{
        "stock_id": "2330", "date": pd.Timestamp("2026-09-01"),
        "open": None, "high": None, "low": None, "close": None,
    }])
    stock_info = pd.DataFrame([{"stock_id": "2330"}])
    with pytest.raises(ValueError, match="missing OHLC"):
        validate(prices, stock_info, pd.Timestamp("2026-09-01").date(), pd.Timestamp("2026-09-01").date())
