# Taiwan Limit-Up Research

台股漲停動能、極端右尾與風控研究專案。

## Data policy

大型行情資料不提交 Git：

- `data/processed/prices.parquet`
- `data/processed/stock_info.parquet`

這兩個檔案由本 repository 的官方資料 builder 建立。為避免研究口徑漂移，不以簡化的 `prev_close × 1.1` 取代官方 tick-size／漲停價邏輯。

## Build the official market dataset

```bash
python -m pip install -r requirements.txt
python src/build_market_data.py --start 2021-01-01 --end 2026-09-15
```

The builder downloads official TWSE and TPEx daily quotes, caches raw responses
so interrupted runs can resume, filters to ordinary shares using the official
company lists, validates the result, and writes:

- `data/processed/prices.parquet`
- `data/processed/stock_info.parquet`
- `data/processed/manifest.json`

To copy the completed snapshot into a mounted or synced Google Drive folder:

```bash
python src/build_market_data.py --publish-dir "/path/to/Google Drive/taiwan-limitup-research"
```

This is a fixed snapshot builder, not a daily updater. Raw prices are not
adjusted for dividends or splits. TPEx official next-session reference/limit
prices are retained when published; no price limit is approximated.

## Expected paths

```text
data/
  processed/
    prices.parquet
    stock_info.parquet
src/
output/
```

## Tests

```bash
pytest -q
```
