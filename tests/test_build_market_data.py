from datetime import date

import pandas as pd

from src.build_market_data import (
    parse_stock_info,
    parse_tpex_daily,
    parse_twse_daily,
    validate,
    is_ordinary_stock_code,
)


DAY = date(2024, 1, 2)


def test_parse_twse_daily_uses_named_fields():
    payload = {"tables": [{"fields": ["證券代號", "成交股數", "成交筆數", "成交金額", "開盤價", "最高價", "最低價", "收盤價"],
                           "data": [["2330", "20,000", "100", "12,000,000", "580.0", "590", "578", "586"]]}]}
    row = parse_twse_daily(payload, DAY)[0]
    assert row["stock_id"] == "2330"
    assert row["market"] == "twse"
    assert row["volume"] == 20_000
    assert row["close"] == 586
    assert row["next_limit_up"] is None


def test_parse_tpex_daily_keeps_official_next_session_limits():
    fields = ["代號", "收盤", "開盤", "最高", "最低", "成交股數", "成交金額(元)", "成交筆數", "次日 參考價", "次日 漲停價", "次日 跌停價"]
    payload = {"tables": [{"fields": fields, "data": [["6488", "100", "98", "101", "97", "1,000", "99,000", "50", "100", "110", "90"]]}]}
    row = parse_tpex_daily(payload, DAY)[0]
    assert row["next_reference_price"] == 100
    assert row["next_limit_up"] == 110
    assert row["next_limit_down"] == 90


def test_stock_info_is_canonical_ordinary_stock_universe():
    twse = [{"公司代號": "2330", "公司簡稱": "台積電", "產業別": "24", "上市日期": "19940905"},
            {"公司代號": "9105", "公司簡稱": "DR", "產業別": "", "上市日期": "20000101"}]
    tpex = [{"SecuritiesCompanyCode": "6488", "CompanyAbbreviation": "環球晶", "SecuritiesIndustryCode": "24", "DateOfListing": "20150925"}]
    result = parse_stock_info(twse, tpex)
    assert result["stock_id"].tolist() == ["6488", "2330"]
    assert result["is_ordinary_stock"].all()


def test_ordinary_stock_code_excludes_funds_drs_and_warrants():
    assert is_ordinary_stock_code("2330")
    assert not is_ordinary_stock_code("0050")
    assert not is_ordinary_stock_code("9105")
    assert not is_ordinary_stock_code("030001")


def test_validate_rejects_duplicate_keys():
    prices = pd.DataFrame([{"stock_id": "2330", "date": pd.Timestamp(DAY), "market": "twse", "open": 1, "high": 1, "low": 1, "close": 1}] * 2)
    info = pd.DataFrame([{"stock_id": "2330"}])
    try:
        validate(prices, info, DAY, DAY)
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicate prices must fail validation")
