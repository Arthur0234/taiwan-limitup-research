# Minimal MA20 exit study

Goal: decide whether the current 3-close-below-MA20 exit is too slow.

## Data
Only `stock_id,date,open,high,low,close`, 2021–2026. MA20 is calculated from close. This study does not depend on legacy official limit-up fields.

Official source references:
- TWSE historical individual daily trading data (available since 2010-01-04).
- TPEx historical individual stock data (available since 1994-01).

## Fixed comparison
- BASE: no MA20/stop exit; max hold 60 trading days.
- MA20_1/2/3: 1/2/3 consecutive closes below MA20.
- STOP_5/7: close <= entry price -5%/-7%.
- Any close-confirmed signal executes at next trading-day open.
- Round-trip cost: 0.4798% (kept from prior study for comparability).

## Inputs
`entries.csv`: `stock_id,entry_date[,entry_price]`.

Entry cohort must be fixed before inspecting exit results. Do not tune entry and exit simultaneously.

## Outputs
`trades.csv`, `summary.csv` with return, win rate, average loss, holding days, and post-exit 5/10/20-day recovery. The decision criterion is downside reduction versus false-exit/recovery cost, not the highest in-sample mean alone.

## Remaining blocker
Need the fixed entry-event cohort. Preferred: recover/reuse the user's existing momentum entry events rather than inventing a new proxy for “pullback + first volume red candle”.
