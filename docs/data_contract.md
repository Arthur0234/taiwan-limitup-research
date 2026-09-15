# Recovered processed-data contract

Status: reconstructed from preserved research code/audits. This is the compatibility target for any replacement builder; it is not evidence that the original parquet binaries have been recovered.

## `data/processed/prices.parquet`

Required by preserved studies:

- `stock_id`: string security code
- `date`: trading date
- `market`: at least `twse` / `tpex`
- `open`, `high`, `low`, `close`: daily prices
- `limit_up`: current-day official upper price limit
- `next_limit_up`: published next-session upper price limit where supplied by the source

Compatibility behavior:

1. Sort by `(stock_id, date)` and require unique keys.
2. For TPEx, preserved studies align the published next-session limit by stock: `published = groupby(stock_id).next_limit_up.shift()` and replace current `limit_up` when available.
3. Limit comparisons use integer cents (`round(price * 100)`) rather than floating-point equality.
4. Historical audit target: price coverage `2020-11-02` through `2026-08-11`.
5. Prices are historically unadjusted in the preserved study; corporate actions therefore remain a known limitation.

## `data/processed/stock_info.parquet`

Required fields:

- `stock_id`: string security code
- `industry_category`: static security/category metadata

Preserved ordinary-stock filter excludes categories:

- `ETF`
- `ETN`
- `上櫃ETF`
- `上櫃指數股票型基金(ETF)`
- `受益證券`
- `存託憑證`
- `指數投資證券(ETN)`

Saved analysis reports 508 excluded security IDs. This is a static metadata filter, not a historical security master.

## Frozen audit targets

Before a replacement dataset is accepted, reproduce or explain deviations from:

- LIMIT_UP Raw: 37,559
- LIMIT_UP Episode: 28,930
- NORMAL Raw: 296,008
- NORMAL Episode: 32,799
- replacement-study event rows: 336,666
- date coverage: 2020-11-02 through 2026-08-11

Execution/cost compatibility:

- signals confirmed at D close; execution at D+1 open
- buy cost: 0.000899
- sell cost: 0.003899
- round trip: 0.004798

## Recovery decision

The original builder/downloader and parquet binaries have not yet been recovered from GitHub or the ChatGPT Library. Do not silently substitute approximate price-limit calculations. A replacement builder must use official TWSE/TPEx data where possible and pass the frozen audits before the MA20 study is unlocked.
