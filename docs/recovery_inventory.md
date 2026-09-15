# Research recovery inventory

Recovered before any new backtest.

## Confirmed prior research

- `momentum_failure_exit_study.py`: fixed failure/exit hypotheses; close-confirmed signals execute next trading-day open.
- `momentum_decay_price_confirmation_exit_study.py`: decay + price-confirmation extension.
- `momentum_replacement_opportunity_cost_study.py`: NO_HIGH_10D replacement/opportunity-cost extension.
- `failure_events.csv`: prior event-level outputs preserved in ChatGPT Library (~382 MB).
- `yearly_robustness.csv`: prior annual robustness outputs preserved in ChatGPT Library.

## Data contract

Expected processed inputs:

- `data/processed/prices.parquet`
- `data/processed/stock_info.parquet`

Prior code confirms daily per-stock OHLC, official limit-price alignment, MA5/10/20 calculation, ETF/ETN/DR exclusions, and data through 2026-08-11.

The large parquet inputs themselves have **not** been recovered from Library/GitHub yet. Do not substitute `prev_close * 1.1` for official Taiwan tick-size / limit-price logic.

## Prior fixed definitions

- Study window: 2021-01-04 through 2026-08-11.
- Observation window: T+1..T+20; failure outcome can extend to failure+10, requiring complete T+30 paths.
- Existing risk baseline: entry-relative -5%, close-confirmed, exit next open; otherwise T+20 close.
- Existing dimensions: DD 3/5/8/10%; MA5/10/20 breaks; no-new-high 3/5/10d.
- Round-trip cost convention: 0.4798%.
- Previous conclusion: -5% is useful as risk control, not established as the predictive thesis cutoff; NO_HIGH_10D is the main decay hypothesis.

## Next study — frozen before execution

Question: compare MA20 persistence exits against fixed entry-relative stops without threshold fishing.

Pre-register:

1. MA20 close-below persistence: 1, 2, 3 consecutive trading-day closes.
2. Fixed stop comparison: -5% and -7% from entry.
3. Confirmation at close; execution at next trading-day open.
4. Same eligible cohorts, costs, and episode definitions as prior study.
5. Report mean/median return, P(loss >=10%), +10/+20 winner retention, right-tail capture, false-exit/recovery, average holding days, and yearly robustness.
6. No optimization after seeing results. Any new threshold becomes a separate validation study.

## Recovery gate

Before execution:

1. Recover or rebuild `prices.parquet` and `stock_info.parquet` from the established formal data builder.
2. Verify schema, duplicate `(stock_id,date)` keys, date range, security exclusions, official limit-price alignment, and cohort counts against saved audit outputs.
3. Only then run the pre-registered MA20 1/2/3-day vs -5%/-7% comparison.
