# Feature Lineage

Each feature's lineage: raw source → columns → transform → feature store location.
Generated from `features/schema.py` and the feature store registry.

---

## Transaction-derived features (source: `data/transactions.db`)

| Feature | Raw Columns | Transform Summary | Store Location |
|---|---|---|---|
| `days_since_last_txn` | `customer_id`, `txn_timestamp`, `signup_date` | `as_of` − `max(txn_timestamp)`; default: tenure | `feature_store/values/days_since_last_txn__v*.parquet` |
| `txn_count_last_90d` | `customer_id`, `txn_timestamp` | `count(*)` in trailing 90 days; default: 0 | `feature_store/values/txn_count_last_90d__v*.parquet` |
| `txn_count_last_30d` | `customer_id`, `txn_timestamp` | `count(*)` in trailing 30 days; default: 0 | `feature_store/values/txn_count_last_30d__v*.parquet` |
| `recent_spend_adjusted_90d` | `customer_id`, `amount`, `is_returned`, `txn_timestamp` | `sum(amount)` with returns penalised at multiplier, winsorized at 99th pct; default: 0.0 | `feature_store/values/recent_spend_adjusted_90d__v*.parquet` |
| `recent_spend_adjusted_30d` | `customer_id`, `amount`, `is_returned`, `txn_timestamp` | Same as 90d but 30-day window, multiplier=0.5; default: 0.0 | `feature_store/values/recent_spend_adjusted_30d__v*.parquet` |
| `return_rate_90d` | `customer_id`, `is_returned`, `txn_timestamp` | `sum(is_returned) / count(*)` in trailing 90d; default: 0.0 | `feature_store/values/return_rate_90d__v*.parquet` |
| `days_to_first_purchase` | `customer_id`, `txn_timestamp`, `signup_date` | `min(txn_timestamp)` − `signup_date`; default: tenure | `feature_store/values/days_to_first_purchase__v*.parquet` |
| `category_entropy_last_90d` | `customer_id`, `category`, `txn_timestamp` | Shannon entropy over category distribution in trailing 90d; default: 0.0 | `feature_store/values/category_entropy_last_90d__v*.parquet` |

## Monthly-aggregate features (source: `data/transactions_monthly_agg.parquet`)

| Feature | Raw Columns | Transform Summary | Store Location |
|---|---|---|---|
| `active_months_last_12m` | `customer_id`, `txn_month`, `txn_count` | Count of months with `txn_count > 0` in trailing 12 months; default: 0 | `feature_store/values/active_months_last_12m__v*.parquet` |

## Profile features (source: `data/customers.csv`)

| Feature | Raw Columns | Transform Summary | Store Location |
|---|---|---|---|
| `tenure_days` | `customer_id`, `signup_date` | `as_of` − `signup_date` (days) | `feature_store/values/tenure_days__v*.parquet` |
| `channel_*` | `acquisition_channel` | One-hot encoded (organic, paid_search, referral, social) | `feature_store/values/channel_*__v*.parquet` |
| `region_*` | `region` | One-hot encoded (east, north, south, west) | `feature_store/values/region_*__v*.parquet` |

---

## Version history (per spec)

The spec defines three versioning axes, all reflected in the registry:

| Feature Family | Parameter | v1 | v2 | Rationale |
|---|---|---|---|---|
| `txn_count_last_90d` (v1) → `txn_count_last_30d` (v2) | `window_days` | 90 | 30 | Shorter window increases sensitivity to recent behaviour change |
| `recent_spend_adjusted_90d` (v1) → `recent_spend_adjusted_30d` (v2) | `window_days` | 90 | 30 | Tied to same window-length parameter as count feature |
| `recent_spend_adjusted_90d` (v1) → `recent_spend_adjusted_90d` (v2) | `return_penalty_multiplier` | 0.5 | 0.75 | Higher multiplier reflects increased return-processing costs |

---

## Multi-source judgment calls

Every feature that could plausibly come from more than one raw source was decided
as documented in `feature_spec.md` § "Multi-source judgment calls". The key principle:
row-level sources for windowed features needing sub-month precision, monthly aggregate
for the 12-month breadth feature where calendar-month grain is sufficient.