#!/usr/bin/env python3
"""Build reusable Taiwan equity market data from official TWSE/TPEx APIs."""

from __future__ import annotations

import argparse
import gzip
import json
import random
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

TWSE_DAILY = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={ymd}&type=ALLBUT0999&response=json"
TPEX_DAILY = "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={ymd}&id=&response=json"
TWSE_INFO = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_INFO = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
USER_AGENT = "taiwan-limitup-research/1.0 (official-market-data-builder)"

PRICE_COLUMNS = [
    "stock_id", "date", "market", "open", "high", "low", "close",
    "volume", "turnover", "transactions", "next_reference_price",
    "next_limit_up", "next_limit_down",
]
RAW_PRICE_COLUMNS = PRICE_COLUMNS + ["security_name"]
INFO_COLUMNS = [
    "stock_id", "name", "market", "industry_code", "industry_category",
    "listing_date", "security_type", "is_ordinary_stock",
]


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--out-dir", default="data/processed")
    parser.add_argument("--cache-dir", default="data/raw/official")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--request-delay", type=float, default=0.15)
    parser.add_argument(
        "--publish-dir",
        help="optional mounted/synced Google Drive folder receiving final parquet files",
    )
    return parser.parse_args()


def fetch_json(url: str, retries: int = 5) -> Any:
    """Fetch JSON with bounded exponential backoff for flaky official endpoints."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urlopen(req, timeout=120) as response:
                return json.loads(response.read().decode("utf-8-sig"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(min(30, 2**attempt) + random.random())
    raise RuntimeError(f"official API failed after {retries} attempts: {url}") from last_error


def _number(value: Any) -> float | None:
    text = str(value).strip().replace(",", "")
    if text in {"", "--", "---", "除權", "除息", "除權息"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def is_ordinary_stock_code(stock_id: str) -> bool:
    """Official equity code convention: four digits, non-fund, non-DR."""
    return (
        len(stock_id) == 4
        and stock_id.isdigit()
        and stock_id[0] != "0"  # funds and exchange-traded notes
        and not stock_id.startswith("91")  # Taiwan depositary receipts
    )


def _table_with_fields(payload: dict[str, Any], required: set[str]) -> dict[str, Any] | None:
    for table in payload.get("tables", []):
        if required.issubset(set(table.get("fields") or [])):
            return table
    return None


def parse_twse_daily(payload: dict[str, Any], day: date) -> list[dict[str, Any]]:
    table = _table_with_fields(payload, {"證券代號", "開盤價", "最高價", "最低價", "收盤價"})
    if table is None:
        return []
    positions = {name: i for i, name in enumerate(table["fields"])}
    rows = []
    for values in table.get("data", []):
        get = lambda name, default=None: values[positions[name]] if name in positions else default
        stock_id = str(get("證券代號", "")).strip()
        if not is_ordinary_stock_code(stock_id):
            continue
        rows.append({
            "stock_id": stock_id, "date": day, "market": "twse",
            "security_name": str(get("證券名稱", "")).strip(),
            "open": _number(get("開盤價")), "high": _number(get("最高價")),
            "low": _number(get("最低價")), "close": _number(get("收盤價")),
            "volume": _integer(get("成交股數")), "turnover": _integer(get("成交金額")),
            "transactions": _integer(get("成交筆數")), "next_reference_price": None,
            "next_limit_up": None, "next_limit_down": None,
        })
    return rows


def parse_tpex_daily(payload: dict[str, Any], day: date) -> list[dict[str, Any]]:
    table = _table_with_fields(payload, {"代號", "開盤", "最高", "最低", "收盤"})
    if table is None:
        return []
    positions = {name: i for i, name in enumerate(table["fields"])}
    rows = []
    for values in table.get("data", []):
        get = lambda name, default=None: values[positions[name]] if name in positions else default
        stock_id = str(get("代號", "")).strip()
        if not is_ordinary_stock_code(stock_id):
            continue
        rows.append({
            "stock_id": stock_id, "date": day, "market": "tpex",
            "security_name": str(get("名稱", "")).strip(),
            "open": _number(get("開盤")), "high": _number(get("最高")),
            "low": _number(get("最低")), "close": _number(get("收盤")),
            "volume": _integer(get("成交股數")), "turnover": _integer(get("成交金額(元)")),
            "transactions": _integer(get("成交筆數")),
            "next_reference_price": _number(get("次日 參考價")),
            "next_limit_up": _number(get("次日 漲停價")),
            "next_limit_down": _number(get("次日 跌停價")),
        })
    return rows


def parse_stock_info(twse: list[dict[str, Any]], tpex: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for market, records, keys in (
        ("twse", twse, ("公司代號", "公司簡稱", "產業別", "上市日期")),
        ("tpex", tpex, ("SecuritiesCompanyCode", "CompanyAbbreviation", "SecuritiesIndustryCode", "DateOfListing")),
    ):
        code_key, name_key, industry_key, listing_key = keys
        for record in records:
            stock_id = str(record.get(code_key, "")).strip()
            # The official company datasets exclude ETFs/ETNs; four digits also excludes DRs/warrants.
            if not is_ordinary_stock_code(stock_id):
                continue
            industry = str(record.get(industry_key, "")).strip()
            listing = pd.to_datetime(str(record.get(listing_key, "")), format="%Y%m%d", errors="coerce")
            rows.append({
                "stock_id": stock_id,
                "name": str(record.get(name_key, "")).strip(),
                "market": market,
                "industry_code": industry,
                "industry_category": industry,
                "listing_date": listing,
                "security_type": "ordinary_stock",
                "is_ordinary_stock": True,
            })
    result = pd.DataFrame(rows, columns=INFO_COLUMNS)
    if result.empty:
        raise ValueError("official company lists returned no ordinary stocks")
    return result.drop_duplicates(["stock_id", "market"]).sort_values(["market", "stock_id"])


def _cache_path(cache_dir: Path, market: str, day: date) -> Path:
    return cache_dir / market / f"{day.isoformat()}.json.gz"


def load_or_fetch(url: str, cache_path: Path, retries: int, delay: float) -> dict[str, Any]:
    if cache_path.exists():
        with gzip.open(cache_path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    payload = fetch_json(url, retries)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    temporary.replace(cache_path)
    time.sleep(delay)
    return payload


def fetch_one(market: str, day: date, cache_dir: Path, retries: int, delay: float) -> list[dict[str, Any]]:
    if market == "twse":
        url = TWSE_DAILY.format(ymd=day.strftime("%Y%m%d"))
        parser = parse_twse_daily
    else:
        url = TPEX_DAILY.format(ymd=day.strftime("%Y/%m/%d"))
        parser = parse_tpex_daily
    payload = load_or_fetch(url, _cache_path(cache_dir, market, day), retries, delay)
    return parser(payload, day)


def weekdays(start: date, end: date):
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)


def validate(prices: pd.DataFrame, stock_info: pd.DataFrame, start: date, end: date) -> None:
    if prices.empty:
        raise ValueError("no price rows were built")
    if prices.duplicated(["stock_id", "date"]).any():
        raise ValueError("duplicate (stock_id, date) keys")
    if not set(prices["stock_id"]).issubset(set(stock_info["stock_id"])):
        raise ValueError("prices contain securities absent from stock_info")
    if prices["date"].min().date() < start or prices["date"].max().date() > end:
        raise ValueError("price dates fall outside requested range")
    missing_ohlc = prices[["open", "high", "low", "close"]].isna().any(axis=1)
    if missing_ohlc.any():
        raise ValueError(f"{int(missing_ohlc.sum())} rows contain missing OHLC")
    invalid = prices[["open", "high", "low", "close"]].le(0).any(axis=1)
    if invalid.any():
        raise ValueError(f"{int(invalid.sum())} rows contain non-positive OHLC")
    if (prices["low"] > prices[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("OHLC low consistency check failed")
    if (prices["high"] < prices[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("OHLC high consistency check failed")


def main() -> None:
    args = cli()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if end < start:
        raise SystemExit("--end must be on or after --start")
    out_dir, cache_dir = Path(args.out_dir), Path(args.cache_dir)

    twse_info = fetch_json(TWSE_INFO, args.retries)
    tpex_info = fetch_json(TPEX_INFO, args.retries)
    stock_info = parse_stock_info(twse_info, tpex_info)
    tasks = [(market, day) for day in weekdays(start, end) for market in ("twse", "tpex")]
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(fetch_one, market, day, cache_dir, args.retries, args.request_delay): (market, day)
            for market, day in tasks
        }
        for completed, future in enumerate(as_completed(futures), 1):
            market, day = futures[future]
            try:
                rows.extend(future.result())
            except Exception as exc:
                raise RuntimeError(f"failed to build {market} {day}") from exc
            if completed % 100 == 0 or completed == len(futures):
                print(f"downloaded {completed}/{len(futures)} market-days", flush=True)

    prices = pd.DataFrame(rows, columns=RAW_PRICE_COLUMNS)
    prices = prices[prices["stock_id"].map(is_ordinary_stock_code)].copy()
    # Preserve delisted stocks observed during the requested period. Current official
    # company lists cannot describe their industry, so that metadata remains unknown.
    observed = (
        prices[["stock_id", "security_name", "market"]]
        .drop_duplicates(["stock_id", "market"], keep="last")
        .rename(columns={"security_name": "name"})
    )
    known = set(zip(stock_info["stock_id"], stock_info["market"]))
    missing = observed[
        ~observed.apply(lambda row: (row.stock_id, row.market) in known, axis=1)
    ].copy()
    if not missing.empty:
        missing["industry_code"] = pd.NA
        missing["industry_category"] = pd.NA
        missing["listing_date"] = pd.NaT
        missing["security_type"] = "ordinary_stock"
        missing["is_ordinary_stock"] = True
        stock_info = pd.concat([stock_info, missing[INFO_COLUMNS]], ignore_index=True)
        stock_info = stock_info.sort_values(["market", "stock_id"])
    prices = prices.drop(columns=["security_name"])
    prices = prices.dropna(subset=["open", "high", "low", "close"])
    prices = prices.drop_duplicates(["stock_id", "date"]).sort_values(["stock_id", "date"])
    prices["date"] = pd.to_datetime(prices["date"])
    for column in ("volume", "turnover", "transactions"):
        prices[column] = prices[column].astype("Int64")
    validate(prices, stock_info, start, end)

    out_dir.mkdir(parents=True, exist_ok=True)
    prices_path, info_path = out_dir / "prices.parquet", out_dir / "stock_info.parquet"
    prices.to_parquet(prices_path, index=False)
    stock_info.to_parquet(info_path, index=False)
    manifest = {
        "built_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "requested_start": start.isoformat(), "requested_end": end.isoformat(),
        "actual_start": prices["date"].min().date().isoformat(),
        "actual_end": prices["date"].max().date().isoformat(),
        "rows": len(prices), "stocks": prices["stock_id"].nunique(),
        "sources": [TWSE_DAILY, TPEX_DAILY, TWSE_INFO, TPEX_INFO],
        "adjusted_prices": False,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.publish_dir:
        publish_dir = Path(args.publish_dir)
        publish_dir.mkdir(parents=True, exist_ok=True)
        for path in (prices_path, info_path, out_dir / "manifest.json"):
            shutil.copy2(path, publish_dir / path.name)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
