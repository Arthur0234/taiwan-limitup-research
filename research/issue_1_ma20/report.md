# Issue #1 — MA20 persistence exit study

## Decision

**KEEP MA20 3D. Do not shorten it to 1D or 2D.**

Shortening the MA20 persistence rule consistently reduces large losses, but it
also lowers mean return and removes more of the right tail. MA20 1D/2D does not
dominate MA20 3D in either primary cohort. The fixed stop remains a separate
risk-control decision:

- **STOP -5%:** strongest protection against losses of at least 10%, with the
  largest winner/mean-return cost.
- **STOP -7%:** weaker protection, but retains more +20% winners.
- **MA20 3D:** better median and right-tail retention than faster MA20 exits;
  it is a thesis-decay rule, not a hard-loss cap.

No threshold was changed after viewing results.

## Primary results

Returns include the fixed 0.4798% round-trip cost. Entry is T0 close; signals
are confirmed at close and execute at the next stock trading-day open.

### A1 — all locked limit-up episodes

| Rule | Mean | Median | P(loss ≥10%) | P(+20%) | +20% winners retained | Tail captured |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| No early exit | 4.48% | -0.33% | 23.98% | 16.93% | 100.00% | 100.00% |
| MA20 1D | 3.31% | -2.35% | 15.89% | 12.65% | 72.30% | 76.32% |
| MA20 2D | 3.44% | -2.35% | 18.79% | 13.67% | 79.66% | 81.90% |
| **MA20 3D** | **3.61%** | **-2.20%** | **20.64%** | **14.48%** | **84.97%** | **86.45%** |
| Stop -5% | 3.84% | -4.95% | 7.80% | 13.91% | 82.21% | 83.22% |
| Stop -7% | 3.96% | -5.14% | 13.90% | 14.97% | 88.44% | 88.86% |

### B — normal momentum episodes

| Rule | Mean | Median | P(loss ≥10%) | P(+20%) | +20% winners retained | Tail captured |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| No early exit | 1.12% | -1.86% | 20.84% | 9.82% | 100.00% | 100.00% |
| MA20 1D | 0.71% | -2.90% | 10.94% | 7.58% | 76.37% | 77.42% |
| MA20 2D | 0.84% | -3.05% | 13.90% | 8.40% | 85.35% | 85.37% |
| **MA20 3D** | **0.96%** | **-3.03%** | **15.71%** | **8.96%** | **91.06%** | **90.41%** |
| Stop -5% | 0.70% | -4.95% | 6.11% | 7.76% | 79.04% | 79.13% |
| Stop -7% | 0.82% | -4.35% | 11.62% | 8.56% | 87.15% | 87.08% |

### A3 — near-limit locked episodes

This higher-quality entry cohort is much less harmed by fixed stops:

| Rule | Mean | Median | P(loss ≥10%) | P(+20%) | +20% winners retained |
| --- | ---: | ---: | ---: | ---: | ---: |
| No early exit | 12.58% | 7.70% | 10.63% | 23.09% | 100.00% |
| MA20 3D | 9.45% | 4.01% | 9.09% | 16.34% | 69.31% |
| Stop -5% | 11.62% | 6.23% | 5.26% | 21.71% | 94.06% |
| Stop -7% | 11.76% | 6.76% | 7.66% | 22.23% | 96.29% |

This supports treating entry quality and exit policy as separate modules.

## Yearly robustness

Against no early exit:

- A1 MA20 1D improved mean return in 0/6 years; MA20 2D and 3D each in 1/6.
- B MA20 1D and 2D improved mean in 2/6 years; MA20 3D in 3/6.
- Every MA20 and fixed-stop rule improved P(loss ≥10%) in 6/6 years for both
  A1 and B.

The trade-off is therefore stable: earlier exits reduce downside, but do not
produce a stable mean-return advantage.

## Cohort and data audit

- Frozen recovered counts: A1 28,930; A2 9,142; A3 1,751; B 32,799.
- Analyzed counts: A1 28,926; A2 9,141; A3 1,750; B 32,791.
- Fourteen overlapping cohort rows were excluded because all belong to 6873
  before its TWSE listing. The legacy data treated its emerging-market history
  as listed/OTC ordinary-stock data; the corrected builder intentionally does
  not. The exact exclusions are saved in `excluded_legacy_events.csv`.
- Prices contain 2,448,100 rows through 2026-08-11 and zero duplicate
  `(stock_id,date)` keys.
- The replacement file begins 2021-01-04 instead of the legacy 2020-11-02
  warm-up. There are 1,306 overlapping cohort rows whose T0 MA20 is therefore
  unavailable. The full-cohort simulation leaves MA20 inactive until it becomes
  calculable; `summary_ma20_ready.csv` excludes these rows as a prespecified
  sensitivity. It gives the same decision.

## Files

- [`frozen_cohort_entries.csv`](https://drive.google.com/file/d/1hD8FZhn4oxCgkdSlq35w95O8DvrX75S7/view?usp=drivesdk):
  recovered fixed event list (stored with the market Parquet files, not in Git).
- `summary.csv`: full-cohort aggregate results.
- `summary_ma20_ready.csv`: warm-up sensitivity.
- `yearly.csv`: calendar-year robustness.
- `audit.json`: execution contract and counts.
- `excluded_legacy_events.csv`: corrected-universe exclusions.

The complete event-rule trade table is generated locally as
`output/ma20_exit/trades.parquet` and is intentionally not committed.
