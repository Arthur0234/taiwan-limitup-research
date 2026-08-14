# Taiwan Limit-Up Research

台股漲停動能、極端右尾與風控研究專案。

## Data policy

大型行情資料不提交 Git：

- `data/processed/prices.parquet`
- `data/processed/stock_info.parquet`

這兩個檔案須由既有正式資料建置流程恢復。為避免研究口徑漂移，不以簡化的 `prev_close × 1.1` 取代官方 tick-size／漲停價邏輯。

## Current recovery scope

目前只允許恢復：

1. `prices.parquet`
2. `stock_info.parquet`

不重跑 feature scan、event dataset、backtest 或研究報告。

## Expected paths

```text
data/
  processed/
    prices.parquet
    stock_info.parquet
src/
output/
```

## Safety

在資料來源與正式 builder 尚未確認前，不執行重建，以免產出和前序研究定義不一致的 parquet。
