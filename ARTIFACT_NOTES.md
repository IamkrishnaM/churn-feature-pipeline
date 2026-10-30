# ARTIFACT_NOTES.md — Self-critique

## Design decisions and trade-offs

### What works well

1. **Single-entry-point parity**: `build_features(as_of, source_paths, customer_ids)` in `build.py` is the only code path for both training and scoring. The only difference is `customer_ids=None` (training) vs `customer_ids=[...]` (scoring). This makes the parity guarantee verifiable with a single test.

2. **Zero-activity defaults baked into each transform**: Every transaction-derived function explicitly handles empty transaction sets via `how="left"` merge + `fillna(default)`. No global catch-all — each feature independently ensures correctness.

3. **Winsorization after window filter**: Fixed in review — `recent_spend_adjusted_Nd` now computes the 99th percentile on in-window amounts only, avoiding future-data leakage into the cap.

4. **Versioned feature names bake parameters in**: `txn_count_last_90d` vs `txn_count_last_30d` encodes the window_days parameter in the name, preventing confusion during model training and making the feature store self-documenting.

5. **Feature store is dependency-free**: SQLite + parquet only. No mlflow, feast, or other external store. Easy to test, easy to reset.

### Known limitations

1. **Entropy via `.apply()`**: `category_entropy_last_90d` uses pandas `.apply()` which is vectorized only within each group. For 1500 customers this is fast enough; at 500k+ customers a numpy vectorization would be needed.

2. **Winsorization at global p99**: The 99th percentile is computed across all transactions in the window, not per-customer. This means the cap is dataset-dependent — a customer could have all their transactions clipped if they fall above p99. A per-customer winsorization might be more robust but changes the feature semantics.

3. **Return rate is undefined for zero-activity customers**: The spec says default 0.0, but a customer with 0 transactions has no "rate." Zero is a reasonable default since it places them in the "no returns" group (same as a customer with transactions but no returns), but this does conflate "no data" with "no returns."

4. **Spend can go negative after return penalty**: `recent_spend_adjusted_Nd` with `return_penalty_multiplier=0.5` can produce negative values if returns dominate. The spec explicitly allows this via the penalty design. The outlier check ensures negative values aren't **too** negative (< -$10,000 after winsorization), but a negative spend is semantically odd for a monetary feature.

5. **Tenure and days-since-last-txn are correlated for zero-activity customers**: The spec notes this explicitly. The model sees both columns; a linear model would need to handle multicollinearity, but tree-based models typically used for churn handle this naturally.

6. **`channel_social` and `region_west` may have zero variance** if the sample doesn't include all categories. The one-hot encoding creates columns for all values present in the source data, but the schema assumes all four channels and four regions exist. If a category is absent in the training set but appears in scoring, the schema will silently produce a column not seen by the model. A production pipeline would union all expected categories upfront.

7. **No versioning for profile features**: Channel and region dummies are registered as v1 only. If a new region appears, there's no version bump mechanism currently — new columns would simply appear. The spec doesn't address this, but it's a gap.

### What would change at scale

- **Parquet partition scheme**: Currently one file per feature per version. At thousands of features this becomes unwieldy. A Hive-style partition layout (`feature_store/values/{feature_name}/version={v}/`) would scale better.
- **Row-group filtering**: The store reads whole parquet files; for large datasets we'd want to push down customer_id filters.
- **Concurrent registrations**: The registry uses SQLite WAL mode but still has a single-writer bottleneck. At high registration throughput this would need a migration to PostgreSQL or similar.

### Test gaps

- No performance/benchmark tests (feature build time, store read time)
- No corruption tests (what happens if a parquet file is truncated on disk)
- No cross-source parity test (txn_count in monthly_agg vs transactions.db for same customer/period)