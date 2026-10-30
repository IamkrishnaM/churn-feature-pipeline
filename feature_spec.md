# feature_spec.md — Churn Feature Pipeline

## Candidate features

### Feature 1: Recency — `days_since_last_txn`

- **Source**: `data/transactions.db`
- **Computation**: `as_of` minus the customer's most recent `txn_timestamp` (in days).
- **Zero-activity default**: `as_of` minus `signup_date` (full tenure). ⚠️ This creates
  linear correlation with `tenure_days` for zero-activity customers — the model will see
  both columns, so this is acceptable but noted.
- **Source justification**: Row-level `txn_timestamp` needed — a gap of a few days is
  meaningful and the monthly aggregate cannot express sub-month recency.
- **Rationale**: Customers who have not transacted recently are disengaging. Distinguish from
  low-frequency-but-loyal (quarterly) customers by comparing gap to their typical
  inter-purchase interval, which this model doesn't explicitly compute — the raw gap is the
  first-order signal.

### Feature 2: Frequency — `txn_count_last_90d` / `txn_count_last_30d`

- **Source**: `data/transactions.db`
- **Computation**: Count of transactions in the trailing N days before `as_of`. N is
  parameterized for versioning (see below). The concrete feature name includes the window
  length (e.g. `txn_count_last_90d` for N=90, `txn_count_last_30d` for N=30).
- **Zero-activity default**: 0
- **Source justification**: Sub-month precision needed for a 90-day or 30-day window — the
  monthly aggregate aligns to calendar months and would shift window boundaries by up to 30
  days.
- **Rationale**: A drop in recent transaction frequency relative to the customer's own
  baseline flags disengagement. This is distinct from recency: a customer may have transacted
  yesterday (good recency) but only once in 90 days (bad frequency).

### Feature 3: Monetary — `recent_spend_adjusted_90d` / `recent_spend_adjusted_30d`

- **Source**: `data/transactions.db`
- **Computation**: Sum of `amount` over trailing N days, with returns penalized:
  `is_returned=0` → +amount, `is_returned=1` → −amount × `return_penalty_multiplier`.
  N and the multiplier are parameterized for versioning. The concrete feature name includes
  the window length.
- **Zero-activity default**: 0.0
- **Source justification**: Same as Feature 2 — sub-month precision needed.
- **Rationale**: Spend trajectory captures customers reducing monetary commitment before
  leaving. A customer who spent $500/quarter then drops to $50 is distinct from one who always
  spent at a low level. The return adjustment distinguishes "still spending but returning more"
  (dissatisfaction) from "spending less overall" (disengagement).
- **Right-skew note**: Amount is right-skewed per `data_dictionary.md`. Winsorize at the
  99th percentile before computing per-customer sums.

### Feature 4: Engagement Breadth — `active_months_last_12m`

- **Source**: `data/transactions_monthly_agg.parquet`
- **Computation**: Count of distinct months (`txn_month`) where `txn_count > 0` in the
  trailing 12 months.
- **Zero-activity default**: 0
- **Source justification**: Natural fit for monthly aggregate — pre-computed, cheaper, correct
  at calendar-month grain. The 12-month window means a ±1-month ETL lag doesn't materially
  change the answer.
- **Rationale**: Customers who concentrate activity into a few months (two big holiday trips)
  differ structurally from those with steady monthly engagement. A drop in active months
  signals the customer is narrowing their relationship with the platform, distinct from
  transaction count (12 txns in one month = active_months=1; one txn/month for a year =
  active_months=12, same count, different pattern).

### Feature 5: Return Rate — `return_rate_90d`

- **Source**: `data/transactions.db`
- **Computation**: `sum(is_returned)` / `count(*)` over trailing 90 days.
- **Zero-activity default**: 0.0
- **Source justification**: 90-day window needs row-level precision.
- **Rationale**: Rising return rate signals product dissatisfaction — a known churn precursor.
  Distinct from low spend: a customer can maintain normal spend while returning more of what
  they buy, suggesting dissatisfaction rather than disengagement.

### Feature 6: Customer Profile (static)

- **Source**: `data/customers.csv`
- **Features**:
  - `tenure_days` = `as_of` − `signup_date`
  - `acquisition_channel` (one-hot encoded: organic, paid_search, referral, social)
  - `region` (one-hot encoded: east, north, south, west)
- **Zero-activity default**: N/A — always present for every customer.
- **Rationale**: Acquisition channel is a natural confound — paid-search customers may have
  different baseline churn risk from organic/referral (different intent, different acquisition
  cost). Tenure captures the well-known effect that newer customers churn more.

### Feature 7: Days to First Purchase — `days_to_first_purchase`

- **Source**: `data/transactions.db` + `data/customers.csv`
- **Computation**: `min(txn_timestamp)` − `signup_date` (in days).
- **Zero-activity default**: Full tenure (`as_of` − `signup_date`) — they still haven't
  purchased.
- **Source justification**: Needs `signup_date` (from customers.csv) and the earliest
  transaction per customer (from transactions.db).
- **Rationale**: An early-warning signal well-established in churn modeling: customers who buy
  within the first week are far more likely to become loyal. A customer who waited 6 months
  before their first purchase has a fundamentally different engagement trajectory from one who
  bought on day one. This is a single per-customer value, not windowed, so it's independent
  of the `as_of` date (except for the zero-activity default).

### Feature 8: Category Entropy — `category_entropy_last_90d`

- **Source**: `data/transactions.db`
- **Computation**: Shannon entropy over the `category` distribution in the trailing 90 days.
  For each distinct category c, let p_c = (transactions in category c) / (total transactions).
  Entropy = −Σ(p_c × log₂(p_c)). Range: 0 (all activity in one category) to log₂(6) ≈ 2.58
  (perfectly spread across all 6 categories).
- **Zero-activity default**: 0.0
- **Source justification**: Needs row-level precision for the 90-day window.
- **Rationale**: Customers who narrow their category breadth before churning (e.g. from 4
  categories to just "grocery") show reduced engagement breadth that RFM alone misses. Someone
  spending $200 across 3 categories is behaviourally different from someone spending $200 all
  in one category — the former explores, the latter relies on a single category. A shrinking
  entropy over time is a churn precursor.

---

## Train/score parity design

- **Shared function/code path**: `build_features(as_of, source_paths=None, customer_ids=None)`
- **Only allowed training/scoring difference**: Training passes `customer_ids=None` (all
  customers); scoring passes an explicit list of one or more `customer_ids`.
- **How `as_of` is threaded**: `as_of` is always a parameter passed into `build_features()`,
  never hardcoded or defaulted inside any transform. Each feature function receives `as_of` and
  filters/truncates data relative to it.
- **Training as-of date**: **2026-03-31**. This provides a ~4-month gap before the latest
  transaction data (2026-07-31), avoiding label leakage while preserving a substantial
  observation window for trailing-window features (90-day windows will have data through
  March 2026; 30-day windows through late February 2026).

---

## Feature store, versioning & lineage

### Features versioned

Two distinct features, each with two versions:

| Feature | Parameter | v1 Value | v2 Value | Reason v2 differs |
|---|---|---|---|---|
| `txn_count_last_90d` (v1) → `txn_count_last_30d` (v2) | `window_days` | 90 | 30 | Shortening the window increases sensitivity to recent behaviour change at the cost of noise. A 30-day window catches rapid disengagement; 90-day window is more stable. |
| `recent_spend_adjusted_90d` (v1) → `recent_spend_adjusted_30d` (v2) | `window_days` | 90 | 30 | Tied to the same window-length parameter as the count feature — both move from 90d to 30d together. |
| `recent_spend_adjusted_90d` (v1) → `recent_spend_adjusted_90d` (v2) | `return_penalty_multiplier` | 0.5 | 0.75 | The multiplier reflects the business's cost of processing returns (restocking, shipping, customer service). If returns become more expensive, the multiplier increases, penalising heavy-return customers more in the adjusted-spend metric. |

### Version bump rules

A version bump happens only when a parameter value, source column, or computation logic changes
materially. Cosmetic changes (renamed columns, reformatted descriptions) do not trigger a bump.

### Lineage requirements

Every lineage entry must let someone reconstruct the feature from raw data without reading
pipeline code. Each entry documents: source file/table + column(s), the transform (one-line
description), the business rationale, any version-specific parameter values, and the
feature-store location (registry table row + parquet path).

---

## Multi-source judgment calls

| Feature | Could come from | Chosen source | Why |
|---|---|---|---|
| `txn_count_last_90d` / `txn_count_last_30d` | Both | `transactions.db` | Window ≤ 90 days needs sub-month precision. Monthly aggregate would shift the window by up to 30 days depending on calendar alignment. |
| `recent_spend_adjusted_90d` / `recent_spend_adjusted_30d` | Both | `transactions.db` | Same as above. Also needs `is_returned` at row level for the penalty computation. |
| `return_rate_90d` | Both | `transactions.db` | Same window-precision argument. |
| `active_months_last_12m` | Both | `transactions_monthly_agg.parquet` | 12-month window at calendar-month grain. Pre-computed, cheaper, and the ETL-lag risk is negligible at this window size. |
| `category_entropy_last_90d` | `transactions.db` only | `transactions.db` | Category detail is lost in the aggregate — the parquet only has counts, not category distributions. |
| `days_to_first_purchase` | `transactions.db` only | `transactions.db` + `customers.csv` | Needs row-level earliest timestamp per customer plus signup date. |
| `days_since_last_txn` | Both | `transactions.db` | Sub-day precision needed — the aggregate's month grain loses the edge. |
| Profile features | `customers.csv` only | `customers.csv` | No alternative source for these attributes. |

---

## Data-quality checks

| Check | What it catches | On failure |
|---|---|---|
| No unexpected nulls after defaulting | A transform silently dropping a customer from the feature DataFrame | `raise` / non-zero exit |
| Zero-activity customers receive 0.0 (or the stated default), not null | A reindex/fillna bug for customers with no transaction history | `raise` / non-zero exit |
| All monetary/aggregate features within sane bounds: `recent_spend_adjusted_90d` / `recent_spend_adjusted_30d` ≥ -$1,000 and < $10,000 (negative by design — return penalty); `return_rate_90d` in [0, 1]; `category_entropy_last_90d` in [0, log₂(6)]; `active_months_last_12m` in [0, 12] | A unit error, duplicate-row join, or out-of-range value from a computation bug | `raise` / non-zero exit |
| Row count matches total customer count (training) or requested `customer_ids` count (scoring) | A join dropping or duplicating customers | `raise` / non-zero exit |
| `txn_count` in parquet is ≤ corresponding DB count for overlapping date ranges (spot-check) | ETL lag creating a material discrepancy for a customer (catches cross-source parity issues) | Log warning only — known asymmetry, not actionable as a hard failure |