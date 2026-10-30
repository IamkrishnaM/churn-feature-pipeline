# Churn Feature Pipeline — Skill README

This skill implements a versioned feature engineering pipeline for e-commerce churn prediction.

## Directory structure (submission root)

```
data/                          # Raw source data (CSV, SQLite, Parquet)
features/                      # Shared feature module
  ├── build.py                 # Single entry point
  ├── ingest.py                # I/O loaders
  ├── transforms.py            # One function per candidate feature
  ├── schema.py                # Versioned output schema
  └── quality_checks.py        # Data-quality checks
feature_store/                 # Local feature store
  ├── store.py                 # SQLite registry + parquet API
  ├── registry.db              # (generated at runtime)
  └── values/                  # (parquet snapshots generated at runtime)
scripts/                       # Runnable entry points
  ├── build_training_features.py
  ├── score_customer.py
  └── compare_feature_versions.py
tests/                         # Test suite (46 tests)
outputs/artifacts/             # Generated reports and docs
  ├── FEATURE_LINEAGE.md
  ├── VERSION_COMPARISON.md
  ├── PARITY_CHECK.md
  ├── ARTIFACT_NOTES.md
  └── review_log.md
skills/churn-feature-pipeline/ # Skill definition
  ├── skill.md
  └── README.md
feature_spec.md                # Confirmed feature design
data_dictionary.md             # Raw data exploration
README.md                      # Project overview and usage
requirements.txt               # Python dependencies
pytest.ini                     # Pytest configuration
```

## Key outputs

- **19 feature versions** registered in `feature_store/registry.db`:
  - 17 features × v1 (all schema features)
  - `recent_spend_adjusted_90d` v2 (return_penalty_multiplier=0.75)
- **VERSION_COMPARISON.md**: Three version comparisons with real distribution stats
- **All quality checks pass**: Nulls, outliers, drift, row count, zero-activity defaults
- **46 tests pass**: Transforms, parity, quality checks, feature store

## Usage

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.build_training_features --as-of 2026-03-31
python -m scripts.score_customer --customer-id 42 --as-of 2026-03-31
python -m scripts.compare_feature_versions
python -m pytest tests/ -v
```