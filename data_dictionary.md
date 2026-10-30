# Data Dictionary — E-commerce Customer Churn Dataset

> **Status: Reviewed and corrected (learner review completed).** This document was initially
> generated from raw-data inspection in Stage 0, then reviewed and corrected. All ⚠️ markers
> from Stage 0 have been either resolved (verified via deeper data inspection) or retained and
> explicitly noted as unresolved. Treat this as ground truth for the build stage.

---

## Business Context (inferred)

This dataset describes an **e-commerce** customer base with ~1,500 customers observed from
**February 2024 through July 2026**. The target variable `churned` (binary) labels ~13.5% of
customers (202 out of 1,500). The business goal is to build features that predict which
customers are at risk of churning.

- **Acquisition channels**: organic (41%), paid_search (29%), referral (20%), social (11%)
  — a multi-channel acquisition mix typical of a mid-sized e-commerce business.
- **Regions**: east (26%), north (25%), west (25%), south (24%) — balanced geographic
  distribution.
- **Signup dates**: span from **2024-02-14** to **2026-07-01**, so customer tenure reaches up to
  ~2 years 4.5 months. Transaction data extends slightly beyond the latest signup date
  (through 2026-07-31), so some customers signed up and had observable activity within the
  same month. A small number of customers signed up very late (2026-07-01) and thus have very
  short observation windows — features for these customers will be based on limited history.

---

## Source 1: `data/customers.csv`

One row per customer. Static or near-static profile data, no temporal dimension (snapshot as
of the data pull).

| Column | Type | Nullable (observed) | Description |
|---|---|---|---|
| `customer_id` | int64 | No | Unique customer identifier. Ranges 1–1500, sequential (no gaps observed). |
| `signup_date` | str → date | No | Date the customer created their account. Format `YYYY-MM-DD`. Range: 2024-02-14 → 2026-07-01. |
| `acquisition_channel` | str (categorical) | No | How the customer was acquired. Values: `organic`, `paid_search`, `referral`, `social`. |
| `region` | str (categorical) | No | Geographic region. Values: `east`, `north`, `south`, `west`. |
| `churned` | int64 (0/1) | No | Target label. 1 = customer has churned, 0 = active. ~13.5% churn rate. |

**Row count**: 1,500 customers.
**Data quality notes**:
- No nulls observed in any column.
- All `customer_id` values in `customers.csv` are within 1–1500 (sequential). However, not
  every customer has transaction records (see cross-source notes below).

---

## Source 2: `data/transactions.db`

SQLite database containing a single table `transactions`. One row per individual transaction
(e-commerce order/event).

**Table: `transactions`**

| Column | Type | Nullable (observed) | Description |
|---|---|---|---|
| `customer_id` | int64 | No | Customer who made the transaction. Indexed. |
| `txn_timestamp` | str (ISO-8601) | No | When the transaction occurred. Sub-second precision. **Range: 2024-03-24 → 2026-07-31** (verified via data inspection). |
| `category` | str (categorical) | No | Product category. Values observed: `apparel`, `grocery`, `home`, `sports`, `electronics`, `beauty`. |
| `channel` | str (categorical) | No | Sales channel. Values observed: `web`, `mobile_app`, `store`. |
| `amount` | float64 | No | Transaction amount in local currency. Right-skewed (typical for e-commerce). |
| `is_returned` | int64 (0/1) | No | Whether this transaction was a return. 1 = return, 0 = purchase. |

**Row count**: ~11,700 rows (estimated from data inspection). File size is 884 KB.

**Data quality notes**:
- **Customers with zero transactions**: Some customer IDs from `customers.csv` do not appear at
  all in `transactions.db`. These customers signed up but never transacted. Any
  transaction-derived feature must explicitly handle this case (default = 0 or neutral, never
  null).
- **Negative amounts / high-value outliers**: ⚠️ *Not fully verified.* The `amount` field is
  confirmed as right-skewed. The build stage must verify whether any amounts are negative
  (which would be unusual for purchase amounts — potentially a data error) or unusually large.
- **Category and channel** values look clean with no unexpected values.
- **Index**: `idx_transactions_customer_id` exists on `customer_id`.

---

## Source 3: `data/transactions_monthly_agg.parquet`

Pre-aggregated monthly summary, one row per customer per calendar month. Produced by pyarrow
25.0.1 / pandas 3.0.5.

| Column | Type | Nullable (observed) | Description |
|---|---|---|---|
| `customer_id` | int64 | No | Customer identifier. |
| `txn_month` | datetime64[us] | No | Calendar month (first day of month, e.g. `2024-09-01`). |
| `txn_count` | int64 | No | Number of transactions by that customer in that month. |
| `total_amount` | float64 | No | Sum of transaction amounts in that month. |
| `return_count` | int64 | No | Count of returned transactions in that month. |

**Row count**: ⚠️ *Not fully verified. File size is ~69 KB, estimated ~5,000+ rows.*

**Data quality notes**:
- This source is an ETL-produced aggregate — the skill spec notes it may disagree with the
  row-level `transactions.db` at the edges (ETL timing, late-arriving records, different
  snapshot times). This matters for windowed features shorter than a month.
- **Not all customers appear** — customers with zero transactions in a given month will
  have no row for that month. It's expected that customers with zero activity across the
  entire observation period will also be absent from this table.
- `return_count` can be 0; `total_amount` can be 0 (both are plausible for a month with
  no purchases or only returns).

---

## Time Dimensions

| Aspect | Detail |
|---|---|
| Customer tenure (signup) | 2024-02-14 → 2026-07-01 |
| Transactions (row-level) | 2024-03-24 → 2026-07-31 |
| Monthly aggregates | ⚠️ *needs verification* — likely 2024-03 → 2026-07 |
| Grain of `customers.csv` | Static per customer (one row) |
| Grain of `transactions.db` | One row per transaction (sub-second) |
| Grain of `transactions_monthly_agg.parquet` | One row per customer per calendar month |
| Potential source disagreement | The parquet aggregate may be ETL-lagged relative to the row-level table, so the latest few days' transactions may appear in the DB but not yet in the parquet. Any feature with a window < ~30 days should use the row-level source. |

---

## Data Quality Realities (detected, not assumed)

1. **Customers with no transactions exist**: Some `customer_id` values in `customers.csv` have
   no matching rows in `transactions.db` — they signed up but never purchased. This is verified
   data reality (not an assumption). Any transaction-derived feature must explicitly handle
   this case (default = 0 or neutral, never null).
2. **Sources may disagree at the edges**: The row-level DB and monthly parquet aggregate may
   have been produced at different times. A customer who transacted yesterday could appear in
   the DB but not yet in the parquet if the ETL runs on a monthly cadence.
3. **Right-skewed amounts**: Transaction amounts are right-skewed (typical for e-commerce).
   Features using `amount` may benefit from log-transform or winsorization.
4. **Returns are explicit**: `is_returned` in the row-level table and `return_count` in the
   aggregate give a clean signal for return behavior.
5. ⚠️ **Duplicate rows**: Not verified in `transactions.db`. Should be checked during the
   build stage.
6. ⚠️ **Out-of-range amounts**: Not verified whether any amounts are negative or implausibly
   high (e.g. > $10,000). The build stage should add a quality check for this.
7. ⚠️ **Transaction count**: Estimated at ~11,700 rows via data inspection but not confirmed
   via SQL query. The build stage ingestion should log and assert the actual count.
8. **Signup dates precede first transactions**: The earliest signup (2024-02-14) is ~5 weeks
   before the earliest transaction (2024-03-24), which is consistent with a typical
   post-signup activation delay. No anomaly here.