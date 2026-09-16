# Entry Edge Study (Issue #2, stage 1)

## Decision

Test whether an existing momentum signal earns enough excess return to justify
moving capital from 0050 into an individual stock.

## Frozen candidates

- `A_NEAR_LIMIT`: T closes at the official limit-up price and T low is within
  1% of that price.
- `B_HIST2`: T closes at the official limit-up price and the stock had at least
  two prior locked limit-ups in the preceding 10 trading sessions.
- `C_NEAR_LIMIT_HIST2`: intersection of A and B.

The 1%, 2-event and 10-session thresholds come from the existing research and
must not be retuned after viewing this study.

## Execution and benchmark

- Signal known at T close; buy the stock and 0050 benchmark at T+1 open.
- Exit both at the same T+5, T+10 or T+20 close.
- Stock net return subtracts the existing 0.4798% round-trip cost.
- 0050 buy-and-hold return over the identical dates is the benchmark.
- Excess return = stock net return - 0050 return.
- Require complete same-stock and benchmark paths; do not replace an
  unavailable ranked candidate after observing future data.

## Robustness and promotion gate

Report Raw and 20-session Episode samples, overall and by calendar year:
mean/median absolute and excess return, win rate, P(+10%), P(+20%), P(-10%),
and probability of beating 0050.

A signal is eligible for later Stop/Exit work only when Episode excess-return
mean and median are positive, it beats 0050 more than 50% of the time, and the
mean excess return is positive in at least 4 of 6 years. No final trading rule
is promoted from this stage alone.

## Data gate

Requires the established official-price dataset:
`data/processed/prices.parquet` and `stock_info.parquet`. The price file must
contain official `limit_up`; an approximate `prev_close * 1.1` substitute is
rejected. It must also contain 0050 rows.
