# Candidate-Feature Proposal — E-commerce Churn Prediction

> **Status: Reviewed and corrected (learner review completed).** This proposal was initially
> drafted in Stage 0 from raw data, then reviewed and corrected. The corrections address:
> verified transaction date ranges, source-column naming alignment with `data_dictionary.md`,
> clearer separation of static profile features, and specific parameter choices for versioned
> features. This proposal is the basis for `feature_spec.md`.

---

## Proposed Feature Families

### 1. Recency — `days_since_last_txn`

- **Source**: `data/transactions.db` (row-level precision needed — a gap of a few days can be
  meaningful, which the monthly aggregate cannot express).
- **Computation**: `as_of` minus the customer's most recent `txn_timestamp`.
- **Zero-activity default**: `as_of` minus `signup_date` (full tenure). This signals a
  customer who signed up but has never returned. ⚠️ *A confound to watch: this default makes
  `days_since_last_txn` linearly correlated with `tenure_days` for zero-activity customers.
  The model would see this combination, so it's acceptable but should be noted.*
- **Rationale**: Customers who have not transacted recently are plausibly disengaging.
  However, this pattern must be distinguished from low-frequency-but-loyal customers (e.g.
  someone who buys once a quarter by habit). A customer whose gap equals their typical
  inter-purchase interval is different from one whose gap is notably wider than usual.

### 2. Frequency — `txn_count_last_90d` (versioned parameter: `window_days`)

- **Source**: `data/transactions.db` (sub-month precision needed for a 90-day window — the
  parquet aggregate aligns to calendar months, which would shift the window boundaries).
- **Computation**: Count of transactions in the trailing N days before `as_of`.
- **Zero-activity default**: 0.
- **Rationale**: A drop in recent transaction frequency relative to the customer's own
  baseline flags disengagement. A customer who normally buys weekly and has transacted once in
  90 days is different from one who has always been a once-a-quarter buyer — the former shows
  a behavior change while the latter is at their normal pace. This is distinct from recency:
  a customer could have transacted yesterday (good recency) but only once in the last 90 days
  (bad frequency).

### 3. Monetary — `recent_spend_adjusted_90d` (versioned parameter: `return_penalty_multiplier`)

- **Source**: `data/transactions.db`.
- **Computation**: Sum of `amount` over trailing 90 days, with returns penalized: non-return
  transactions (where `is_returned=0`) contribute `+amount`; returned transactions
  (`is_returned=1`) contribute `-amount * return_penalty_multiplier`. The penalty multiplier
  captures that a return economically offsets only a fraction of the original purchase value
  (the business still incurred fulfillment costs). Default multiplier: 0.5. ⚠️ *The specific
  multiplier value is a starting point; it should be calibrated against the business's actual
  return-cost model.*
- **Zero-activity default**: 0.0.
- **Rationale**: Spend trajectory captures customers who are reducing their monetary
  commitment before leaving. A customer who spent \$500/quarter for a year then drops to \$50 is
  distinct from one who always spent at a low level. The return adjustment distinguishes
  "still spending but returning more" (dissatisfaction signal) from "spending less overall"
  (disengagement signal). These can coincide but mean different things.
- **Right-skew note**: `amount` is right-skewed per `data_dictionary.md`. Consider
  winsorizing at the 99th percentile before computing sums, or log-transforming the final
  feature.

### 4. Engagement Breadth — `active_months_last_12m`

- **Source**: `data/transactions_monthly_agg.parquet` (natural fit — this is exactly what a
  monthly aggregate is designed for).
- **Computation**: Count of distinct months in which the customer had at least one transaction
  (`txn_count > 0`) in the trailing 12 months, using the `txn_month` column from the parquet
  file.
- **Zero-activity default**: 0.
- **Rationale**: Customers who concentrate their activity into a few months (e.g. two big
  holiday shopping trips) are structurally different from those with steady monthly
  engagement. A drop in active months signals the customer is narrowing their relationship
  with the platform, which can precede full churn. This is distinct from transaction count:
  a customer could make 12 transactions in one month (active_months=1, high count) vs. one
  transaction per month for a year (active_months=12, same count but different engagement
  pattern).

### 5. Return Rate — `return_rate_90d`

- **Source**: `data/transactions.db` (needs row-level precision for the 90-day window).
- **Computation**: `sum(is_returned)` / `count(*)` over trailing 90 days. For customers with
  zero transactions, default = 0.0.
- **Zero-activity default**: 0.0.
- **Rationale**: Rising return rate signals product dissatisfaction or unmet expectations, a
  well-known churn precursor in e-commerce. This is distinct from low spend: a customer can
  maintain normal spend levels while returning more of what they buy (e.g. spending $500 but
  returning $400 in items), which suggests dissatisfaction rather than disengagement.

### 6. Customer Profile Features (static)

- **Source**: `data/customers.csv`.
- **Features**: `tenure_days` (days since signup), `acquisition_channel` (one-hot or target
  encoded), `region` (one-hot).
- **Computation**: Direct column reads. `tenure_days` = `as_of - signup_date`.
- **Zero-activity default**: N/A — these are always present for every customer.
- **Rationale**: Acquisition channel is a natural confound: paid-search customers may differ
  systematically from organic or referral customers in their baseline churn risk (different
  intent, different acquisition cost). Tenure captures the well-known effect that newer
  customers churn at higher rates.

---

## Feature Engineering Design Decisions (first pass)

| Decision | Proposal | Why |
|---|---|---|
| Which source for short window features? | `transactions.db` | Monthly aggregate loses intra-month precision. For windows ≤ 90 days, a calendar-month grain can shift the effective window by up to 30 days. |
| Which source for monthly/annual features? | `transactions_monthly_agg.parquet` | Pre-computed, cheaper to read, and correct at calendar-month grain. |
| How to handle customers not in `transactions.db`? | Explicit defaults (0, 0.0, tenure) applied via left-join from `customers.csv` — never null. |  ⚠️ *Some customers have no transaction records.* |
| How to handle right-skew in `amount`? | Winsorize at 99th percentile before computing aggregated spend features. | Standard practice for e-commerce spend distributions. |
| Does the static profile table need versioning? | No — these are near-immutable attributes. If signup date is wrong it's a data error, not something we version. | Versioning is for computed features whose parameters may be recalibrated. |

---

## Versioning Candidates (preliminary)

The following features are natural candidates for versioning because they take a tunable
parameter that a business or modeling team might recalibrate:

| Feature | Tunable Parameter | v1 Value | v2 Value | Rationale for Change |
|---|---|---|---|---|
| `txn_count_last_Nd` | `window_days` | 90 | 30 | Shortening the window increases sensitivity to recent behavior change at the cost of noise. Different churn definitions (30-day vs. 90-day inactivity) may prefer one over the other. |
| `recent_spend_adjusted_Nd` | `return_penalty_multiplier` | 0.5 | 0.75 | The multiplier on return amounts reflects the business's cost of processing returns (restocking, shipping, customer service). If returns become more expensive, the multiplier should increase, penalizing heavy-return customers more in the adjusted spend metric. |

These values are confirmed for the build stage. Additional features and versions can be added
in `feature_spec.md`.

---

## Open Questions (resolved during review)

1. **Churn definition**: The `churned` column is a binary label (1 = churned, 0 = active)
   provided as-is. The exact timing of the churn event relative to data is not specified in
   the raw data; treat churn as a post-window label. The build stage should use an `as_of`
   date that precedes the churn label to avoid leakage.
2. **As-of date**: Recommended default `as_of` for training = **2026-05-31**, leaving a ~2-month
   gap before the latest transaction data (2026-07-31) to avoid label leakage. The exact date
   should be parameterized.
3. **Feature gaps**: `category` and `channel` diversity features are deferred from this
   proposal but are worth considering in a future iteration (e.g. `n_unique_categories`,
   `preferred_channel`). They're omitted here because their marginal predictive value over
   spend/frequency/recency features is unclear and would need validation.
4. **Feature crossing**: Deferred. Interaction features add dimensionality; start with main
   effects and add interactions only if the feature set proves insufficient.
5. **Business requirements**: No separate business requirements document was provided. The
   rationales above are inferred from the data alone.