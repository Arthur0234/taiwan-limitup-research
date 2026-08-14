# Minimal Data Recovery

## Authorized scope

Only restore:

- `data/processed/prices.parquet`
- `data/processed/stock_info.parquet`

Do **not** rerun any research pipeline.

## Required provenance before rebuilding

A valid recovery must identify the original:

1. raw data source or local raw files;
2. universe filter;
3. column mapping;
4. official limit-up / tick-size implementation;
5. trading-calendar handling;
6. date range and end-of-data censoring.

If the original builder is unavailable, stop instead of silently substituting a new limit-up calculation.

## Expected minimum schema

The prior analyses referenced these price fields:

- `stock_id`
- `date`
- `open`
- `high`
- `low`
- `close`
- `limit_up`
- `next_limit_up`
- `market`

The stock metadata referenced:

- `stock_id`
- `industry_category`

This list is an audit aid, not authority to recreate missing methodology.
