# Minimal MA20 exit study

Goal: decide whether the current 3-close-below-MA20 exit is too slow, using the
frozen historical cohorts rather than a newly optimized entry sample.

## Data
Only `stock_id,date,open,high,low,close`, 2021–2026. MA20 is calculated from
close. Cohort membership is frozen in
`research/issue_1_ma20/frozen_cohort_entries.csv`, recovered from the preserved
legacy event output. This study does not reclassify events using the replacement
builder.

Official source references:
- TWSE historical individual daily trading data (available since 2010-01-04).
- TPEx historical individual stock data (available since 1994-01).

## Fixed comparison
- NO_EARLY_EXIT: no MA20/stop exit; T+20 close.
- MA20_1/2/3: 1/2/3 consecutive closes below MA20.
- STOP_5/7: close <= entry price -5%/-7%.
- Any close-confirmed signal executes at next trading-day open.
- Entry is the frozen T0 close.
- Round-trip cost: 0.4798% (kept from prior study for comparability).

## Inputs
The fixed file contains `stock_id,entry_date,regime,variant`. Expected Episode
counts are 28,930 / 9,142 / 1,751 / 32,799 for A1 / A2 / A3 / B.
Download the frozen file from
[Google Drive](https://drive.google.com/file/d/1hD8FZhn4oxCgkdSlq35w95O8DvrX75S7/view?usp=drivesdk)
to the default path before rerunning the study.

## Outputs
`trades.parquet`, `summary.csv`, `summary_ma20_ready.csv`, `yearly.csv`,
and `audit.json`. The decision criterion is downside reduction versus
false-exit/recovery and right-tail retention, not the highest in-sample mean.

## Known data boundary

The replacement price file starts at 2021-01-04, while the legacy file had
2020-11-02 warm-up rows. `summary_ma20_ready.csv` therefore reports the
predeclared sensitivity excluding entries whose T0 MA20 is unavailable. The
full-cohort result remains in `summary.csv`; the warm-up limitation must be
reported, not hidden by changing cohort membership after seeing results.
