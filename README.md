# Churn Feature Engineering Pipeline

A production-quality feature engineering pipeline for e-commerce churn prediction,
built from three heterogeneous raw data sources with a local feature store,
versioning, and train/score parity.

## Data sources

| Source | Format | Contents |
|---|---|---|
| `data/customers.csv` | CSV | ~1500 customer profiles (signup_date, acquisition_channel, region, churned) |
| `data/transactions.db` | SQLite | ~11,700 row-level transactions (txn_timestamp, category, amount, is_returned) |
| `data/transactions_monthly_agg.parquet` | Parquet | Pre-aggregated monthly stats per customer (txn_count, total_amount, return_count) |

## Setup

```bash
# Create virtual environment (one time)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Feature spec

The confirmed feature design is in `feature_spec.md`. It defines 8 candidate feature
families (18 columns including one-hot encodings) with:

- **Versioning**: 3 version axes across 2 feature families (window_days 90→30 for count
  and spend; return_penalty_multiplier 0.5→0.75 for spend)
- **Zero-activity defaults**: Every transaction-derived feature handles customers with no
  transactions (default: 0/int/float or full tenure)
- **Multi-source decisions**: Every feature that could come from >1 source has a justified
  choice (`feature_spec.md` § "Multi-source judgment calls")
- **5 data-quality checks**: Nulls, outliers, row count, zero-activity defaults, drift

## Running the pipeline

### 1. Build training features and register in the feature store

```bash
python -m scripts.build_training_features --as-of 2026-03-31
```

This builds features for all ~1500 customers, runs quality checks, and registers 17
features × v1 + `recent_spend_adjusted_90d` v2 (19 registry entries).

### 2. Score a single customer

```bash
python -m scripts.score_customer --customer-id 42 --as-of 2026-03-31
```

Uses the exact same `build_features()` entry point. Feature values for customer 42
will be identical to the training output (parity guarantee).

### 3. Compare feature versions

```bash
python -m scripts.compare_feature_versions
```

Generates `VERSION_COMPARISON.md` with distribution comparisons, rank-order changes,
and interpretation for each versioned feature.

## Running tests

```bash
python -m pytest tests/ -v
```

46 tests across 4 suites:

| Test file | Tests | What it covers |
|---|---|---|
| `tests/test_transforms.py` | 20 | Each feature function: normal, zero-activity, single-record, boundary |
| `tests/test_parity.py` | 2 | Train/scoring paths produce identical features for same customer |
| `tests/test_quality_checks.py` | 14 | Each check passes on clean input, fails on deliberately bad input |
| `tests/test_feature_store.py` | 7 | Registration, retrieval, is_latest, list_versions, error handling |

## Project structure

```
├── features/                  # Shared feature module
│   ├── build.py               # ONE entry point: build_features(as_of, ...)
│   ├── ingest.py              # I/O loaders for 3 raw sources
│   ├── transforms.py          # One pure function per candidate feature
│   ├── schema.py              # Versioned output schema (18 FeatureSpec entries)
│   └── quality_checks.py      # 5 data-quality checks + run_all_checks
├── feature_store/             # Local feature store
│   ├── store.py               # SQLite registry + parquet values API
│   ├── registry.db            # (created at runtime)
│   └── values/                # (parquet snapshots created at runtime)
├── scripts/                   # Runnable entry points
│   ├── build_training_features.py
│   ├── score_customer.py
│   └── compare_feature_versions.py
├── tests/                     # Test suite (46 tests)
├── data/                      # Raw source data
├── feature_spec.md            # Confirmed feature design
├── data_dictionary.md         # Raw data exploration notes
├── candidate_features_proposal.md
├── outputs/artifacts/           # Generated reports
│   ├── VERSION_COMPARISON.md
│   ├── FEATURE_LINEAGE.md
│   ├── PARITY_CHECK.md
│   ├── ARTIFACT_NOTES.md
│   └── review_log.md
├── skills/churn-feature-pipeline/
│   ├── skill.md
│   └── README.md
├── feature_spec.md
```

## Key design decisions

- **Single code path for train/score**: `build_features(as_of, source_paths, customer_ids)`
  is the only feature-build function. The only difference between training and scoring is
  which `customer_ids` are selected. Verified by `test_parity.py`.
- **Versioned feature names encode parameters**: `txn_count_last_90d` not
  `txn_count_last_Nd` — the parameter value is baked into the name, preventing confusion.
- **No external dependencies for the feature store**: SQLite registry + parquet value
  snapshots. No mlflow, feast, or other services.
- **Zero-activity defaults per transform**: Each function independently handles the
  no-transactions case at the merge step, not via a global fillna.


## Deliverables checklist

- [x] `data_dictionary.md` and `candidate_features_proposal.md` (Stage 0)
- [x] `feature_spec.md` with confirmed decisions (source, default, rationale, versioning)
- [x] Shared feature module: `features/build.py`, `ingest.py`, `transforms.py`, `schema.py`
- [x] 5 data-quality checks in `features/quality_checks.py`
- [x] Local feature store with SQLite registry + parquet: `feature_store/store.py`
- [x] Build script: `scripts/build_training_features.py`
- [x] Score script: `scripts/score_customer.py`
- [x] Version comparison script: `scripts/compare_feature_versions.py`
- [x] Test suite (46 tests, all passing)
- [x] `FEATURE_LINEAGE.md`, `PARITY_CHECK.md`, `ARTIFACT_NOTES.md`, `review_log.md`
- [x] `VERSION_COMPARISON.md` with real numbers and interpretation
- [x] `feature_store/registry.db` and `feature_store/values/*.parquet` (19 versions)
- [ ] `starter_code/` — reference starter files (provided by assignment)

## Author

Built using [Claude Code](https://claude.com/claude-code) with human review and
validation of every deliverable. See `review_log.md` for the full audit trail.