#!/usr/bin/env python3
"""Restore the research dataset without crawling TWSE/TPEx website backends.

TWSE OHLC is fetched from FinMind's documented per-security API.  TPEx is read
from the already completed official daily cache.  Every remote response is
cached, requests are serialized, and client/quota errors stop the run.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from src.build_market_data import INFO_COLUMNS, is_ordinary_stock_code, parse_tpex_daily, validate


FINMIND_API = "https://api.finmindtrade.com/api/v4/data"
TWSE_COMPANY_INFO_API = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
USER_AGENT = "taiwan-limitup-research/1.1 (personal-research-data-restore)"
# 6806 is temporarily absent from the current-company OpenAPI snapshot, but
# TWSE's listing announcement records first trading on 2021-11-15.
TWSE_LISTING_DATE_OVERRIDES = {"6806": date(2021, 11, 15)}
PRICE_COLUMNS = [
    "stock_id", "date", "market", "open", "high", "low", "close",
    "volume", "turnover", "transactions", "reference_price", "limit_up",
    "limit_down", "next_reference_price", "next_limit_up", "next_limit_down",
]


class ClientStop(RuntimeError):
    """An error that must stop the downloader rather than be retried."""


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2026-09-15")
    parser.add_argument("--out-dir", default="data/processed")
    parser.add_argument("--finmind-cache", default="data/raw/finmind")
    parser.add_argument("--tpex-cache", default="data/raw/official/tpex")
    parser.add_argument(
        "--twse-company-info-cache",
        default="data/raw/official/twse_company_info.json.gz",
    )
    parser.add_argument("--token-env", default="FINMIND_TOKEN")
    parser.add_argument("--request-delay", type=float, default=0.0)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--min-start-interval", type=float, default=13.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--publish-dir")
    return parser.parse_args()


def fetch_finmind(parameters: dict[str, str], token: str, retries: int = 3) -> list[dict[str, Any]]:
    query = urlencode(parameters)
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"{FINMIND_API}?{query}", headers=headers)
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8-sig"))
            status = int(payload.get("status", 0))
            if status != 200:
                raise ClientStop(f"FinMind stopped the request: {status} {payload.get('msg')}")
            return payload.get("data", [])
        except HTTPError as exc:
            if 400 <= exc.code < 500:
                raise ClientStop(f"FinMind HTTP {exc.code}; stop and fix quota/token/parameters") from exc
            last_error = exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = exc
        if attempt + 1 < retries:
            time.sleep(min(60, 2 ** attempt) + random.random())
    raise RuntimeError("FinMind failed after bounded server/network retries") from last_error


def fetch_public_json(url: str, retries: int = 3) -> Any:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8-sig"))
        except HTTPError as exc:
            if 400 <= exc.code < 500:
                raise ClientStop(f"official OpenAPI HTTP {exc.code}; stop and inspect") from exc
            last_error = exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = exc
        if attempt + 1 < retries:
            time.sleep(min(60, 2 ** attempt) + random.random())
    raise RuntimeError("official OpenAPI failed after bounded retries") from last_error


def load_twse_listing_dates(
    company_info_cache: Path, finmind_cache: Path, retries: int,
) -> dict[str, date]:
    if company_info_cache.exists():
        with gzip.open(company_info_cache, "rt", encoding="utf-8") as handle:
            company_rows = json.load(handle)
    else:
        company_rows = fetch_public_json(TWSE_COMPANY_INFO_API, retries)
        company_info_cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = company_info_cache.with_suffix(".tmp")
        with gzip.open(temporary, "wt", encoding="utf-8") as handle:
            json.dump(company_rows, handle, ensure_ascii=False)
        temporary.replace(company_info_cache)

    dates: dict[str, date] = {}
    for row in company_rows:
        stock_id = str(row.get("公司代號", "")).strip()
        raw_date = str(row.get("上市日期", "")).strip()
        if stock_id and len(raw_date) == 8 and raw_date.isdigit():
            dates[stock_id] = datetime.strptime(raw_date, "%Y%m%d").date()

    # FinMind keeps an `emerging` row whose date ends at the market transfer.
    # This fallback covers securities that have since transferred away from TWSE.
    info_path = finmind_cache / "stock_info.json.gz"
    with gzip.open(info_path, "rt", encoding="utf-8") as handle:
        for row in json.load(handle):
            if str(row.get("type", "")).lower() != "emerging":
                continue
            stock_id = str(row.get("stock_id", "")).strip()
            ended = pd.to_datetime(row.get("date"), errors="coerce")
            if stock_id and not pd.isna(ended) and stock_id not in dates:
                dates[stock_id] = ended.date() + pd.Timedelta(days=1)
    dates.update(TWSE_LISTING_DATE_OVERRIDES)
    return dates


def load_stock_info(cache_dir: Path, token: str, retries: int) -> pd.DataFrame:
    path = cache_dir / "stock_info.json.gz"
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            records = json.load(handle)
    else:
        records = fetch_finmind({"dataset": "TaiwanStockInfo"}, token, retries)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        with gzip.open(temporary, "wt", encoding="utf-8") as handle:
            json.dump(records, handle, ensure_ascii=False)
        temporary.replace(path)

    rows = []
    for record in records:
        market = str(record.get("type", "")).lower()
        stock_id = str(record.get("stock_id", "")).strip()
        if market not in {"twse", "tpex"} or not is_ordinary_stock_code(stock_id):
            continue
        rows.append({
            "stock_id": stock_id,
            "name": str(record.get("stock_name", "")).strip(),
            "market": market,
            "industry_code": pd.NA,
            "industry_category": str(record.get("industry_category", "")).strip() or pd.NA,
            "listing_date": pd.to_datetime(record.get("date"), errors="coerce"),
            "security_type": "ordinary_stock",
            "is_ordinary_stock": True,
        })
    result = pd.DataFrame(rows, columns=INFO_COLUMNS)
    if result.empty:
        raise ValueError("FinMind stock info returned no TWSE/TPEx ordinary stocks")
    return result.sort_values("listing_date").drop_duplicates(["stock_id", "market"], keep="last")


def tick_size(price: float) -> float:
    if price < 10:
        return 0.01
    if price < 50:
        return 0.05
    if price < 100:
        return 0.1
    if price < 500:
        return 0.5
    if price < 1000:
        return 1.0
    return 5.0


def _price_on_tick(raw: Decimal, upper: bool) -> float:
    """Round toward the reference price using the tick at the resulting price."""
    tick = Decimal(str(tick_size(float(raw))))
    direction = ROUND_FLOOR if upper else ROUND_CEILING
    candidate = (raw / tick).to_integral_value(rounding=direction) * tick
    # Crossing 10/50/100/500/1000 can change the valid tick. Re-evaluate once.
    final_tick = Decimal(str(tick_size(float(candidate))))
    if final_tick != tick:
        candidate = (raw / final_tick).to_integral_value(rounding=direction) * final_tick
    if candidate <= 0:
        raise ValueError("price limit must be positive")
    return float(candidate)


def price_limits(reference: float) -> tuple[float, float]:
    value = Decimal(str(reference))
    return _price_on_tick(value * Decimal("1.10"), upper=True), _price_on_tick(value * Decimal("0.90"), upper=False)


def parse_finmind_prices(records: list[dict[str, Any]], market: str) -> pd.DataFrame:
    rows = []
    for record in records:
        close = float(record.get("close") or 0)
        open_ = float(record.get("open") or 0)
        high = float(record.get("max") or 0)
        low = float(record.get("min") or 0)
        if min(open_, high, low, close) <= 0:
            continue
        spread = float(record.get("spread") or 0)
        reference = round(close - spread, 2)
        upper, lower = price_limits(reference)
        rows.append({
            "stock_id": str(record["stock_id"]), "date": pd.Timestamp(record["date"]),
            "market": market, "open": open_, "high": high, "low": low, "close": close,
            "volume": int(record.get("Trading_Volume") or 0),
            "turnover": int(record.get("Trading_money") or 0),
            "transactions": int(record.get("Trading_turnover") or 0),
            "reference_price": reference, "limit_up": upper, "limit_down": lower,
            "next_reference_price": None, "next_limit_up": None, "next_limit_down": None,
        })
    return pd.DataFrame(rows, columns=PRICE_COLUMNS)


def load_twse_prices(
    stock_info: pd.DataFrame, cache_dir: Path, start: date, end: date,
    token: str, retries: int, delay: float, workers: int = 2, min_start_interval: float = 13.0,
    listing_dates: dict[str, date] | None = None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    ids = sorted(stock_info.loc[stock_info.market.eq("twse"), "stock_id"].unique())
    price_dir = cache_dir / "prices"
    price_dir.mkdir(parents=True, exist_ok=True)
    rate_lock = threading.Lock()
    next_start = [time.monotonic()]

    def load_one(stock_id: str) -> pd.DataFrame:
        path = price_dir / f"{stock_id}_{start}_{end}.json.gz"
        if path.exists():
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                records = json.load(handle)
        else:
            with rate_lock:
                wait = next_start[0] - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                next_start[0] = time.monotonic() + min_start_interval
            records = fetch_finmind({
                "dataset": "TaiwanStockPrice", "data_id": stock_id,
                "start_date": start.isoformat(), "end_date": end.isoformat(),
            }, token, retries)
            temporary = path.with_suffix(".tmp")
            with gzip.open(temporary, "wt", encoding="utf-8") as handle:
                json.dump(records, handle, ensure_ascii=False)
            temporary.replace(path)
            if delay:
                time.sleep(delay)
        frame = parse_finmind_prices(records, "twse")
        listed_from = (listing_dates or {}).get(stock_id)
        if listed_from is not None and not frame.empty:
            frame = frame[frame["date"] >= pd.Timestamp(listed_from)]
        return frame

    # FinMind documents a 300 requests/hour free limit. Two workers hide network
    # latency, while the global 13-second start interval caps this process below
    # 277 requests/hour and prevents bursts.
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 2))) as pool:
        futures = {pool.submit(load_one, stock_id): stock_id for stock_id in ids}
        for completed, future in enumerate(as_completed(futures), 1):
            frame = future.result()
            if not frame.empty:
                frames.append(frame)
            if completed % 25 == 0 or completed == len(ids):
                print(f"TWSE FinMind cache {completed}/{len(ids)} stocks", flush=True)
    if not frames:
        raise ValueError("no TWSE prices were restored")
    return pd.concat(frames, ignore_index=True)


def load_tpex_prices(cache_dir: Path, start: date, end: date) -> pd.DataFrame:
    frames = []
    for path in sorted(cache_dir.glob("*.json.gz")):
        day = date.fromisoformat(path.name[:10])
        if not start <= day <= end:
            continue
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            records = parse_tpex_daily(json.load(handle), day)
        if records:
            frames.append(pd.DataFrame(records))
    if not frames:
        raise ValueError("no TPEx official cache was found")
    data = pd.concat(frames, ignore_index=True).sort_values(["stock_id", "date"])
    grouped = data.groupby("stock_id", sort=False)
    data["reference_price"] = grouped["next_reference_price"].shift(1)
    data["limit_up"] = grouped["next_limit_up"].shift(1)
    data["limit_down"] = grouped["next_limit_down"].shift(1)
    data["date"] = pd.to_datetime(data["date"])
    # TPEx can publish volume/turnover from non-regular sessions while the
    # regular-session OHLC fields remain `--`. Those rows have no usable daily
    # bar and must not enter OHLC research.
    data = data.dropna(subset=["open", "high", "low", "close"])
    return data[PRICE_COLUMNS]


def audit_tick_rule(tpex: pd.DataFrame) -> dict[str, int | float]:
    sample = tpex.dropna(subset=["next_reference_price", "next_limit_up", "next_limit_down"])
    mismatches = 0
    for row in sample.itertuples():
        upper, lower = price_limits(float(row.next_reference_price))
        mismatches += upper != float(row.next_limit_up) or lower != float(row.next_limit_down)
    total = len(sample)
    exact_rate = (total - mismatches) / total if total else 0.0
    if exact_rate < 0.995:
        raise ValueError(f"tick-size exact rate is unexpectedly low: {exact_rate:.4%}")
    return {"rows": total, "exact": total - mismatches, "exceptions": mismatches, "exact_rate": exact_rate}


def main() -> None:
    args = cli()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if end < start:
        raise SystemExit("--end must be on or after --start")
    finmind_cache, out_dir = Path(args.finmind_cache), Path(args.out_dir)
    token = os.environ.get(args.token_env, "")

    stock_info = load_stock_info(finmind_cache, token, args.retries)
    listing_dates = load_twse_listing_dates(
        Path(args.twse_company_info_cache), finmind_cache, args.retries,
    )
    tpex = load_tpex_prices(Path(args.tpex_cache), start, end)
    tick_audit = audit_tick_rule(tpex)
    twse = load_twse_prices(
        stock_info, finmind_cache, start, end, token, args.retries, args.request_delay,
        args.workers, args.min_start_interval, listing_dates,
    )
    # The per-security FinMind history may include periods when the same code
    # traded on TPEx. Prefer the preserved official TPEx row at that grain.
    tpex_keys = pd.MultiIndex.from_frame(tpex[["stock_id", "date"]])
    twse_keys = pd.MultiIndex.from_frame(twse[["stock_id", "date"]])
    twse = twse[~twse_keys.isin(tpex_keys)]
    prices = pd.concat([twse, tpex], ignore_index=True)
    prices = prices[prices.stock_id.map(is_ordinary_stock_code)].copy()
    prices = prices.drop_duplicates(["stock_id", "date"]).sort_values(["stock_id", "date"])
    for column in ("volume", "turnover", "transactions"):
        prices[column] = prices[column].astype("Int64")

    observed = set(prices.stock_id)
    stock_info = stock_info[stock_info.stock_id.isin(observed)].copy()
    validate(prices, stock_info, start, end)
    out_dir.mkdir(parents=True, exist_ok=True)
    prices_path = out_dir / "prices.parquet"
    info_path = out_dir / "stock_info.parquet"
    prices.to_parquet(prices_path, index=False)
    stock_info.to_parquet(info_path, index=False)
    manifest = {
        "built_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "requested_start": start.isoformat(), "requested_end": end.isoformat(),
        "actual_start": prices.date.min().date().isoformat(),
        "actual_end": prices.date.max().date().isoformat(),
        "rows": len(prices), "stocks": prices.stock_id.nunique(),
        "sources": {
            "twse_ohlc": "FinMind TaiwanStockPrice per-security API",
            "tpex_ohlc_and_limits": "preserved TPEx official daily cache",
            "stock_info": "FinMind TaiwanStockInfo",
        },
        "adjusted_prices": False,
        "twse_limit_price_note": "Calculated from FinMind reference price and standard TWSE tick rules; special-limit/no-limit cases may differ.",
        "tpex_tick_rule_audit": tick_audit,
        "license_note": "Personal research use; attribute original providers; do not redistribute raw data.",
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.publish_dir:
        import shutil
        publish_dir = Path(args.publish_dir)
        publish_dir.mkdir(parents=True, exist_ok=True)
        for path in (prices_path, info_path, manifest_path):
            shutil.copy2(path, publish_dir / path.name)
    print(json.dumps(manifest, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
