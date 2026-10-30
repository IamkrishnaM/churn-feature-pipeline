# Parity Check — Train/Score Feature Consistency

## Guarantee

The pipeline guarantees that `build_features(as_of, source_paths, customer_ids)` produces
identical feature values for a given `(customer_id, as_of)` regardless of whether it was
called from the training path (`customer_ids=None`, builds all customers) or the scoring
path (`customer_ids=[42]`, builds one customer).

## How it's enforced

1. **Single code path**: `build.py` `build_features()` is the *only* function that constructs
   the feature DataFrame. Both `scripts/build_training_features.py` and
   `scripts/score_customer.py` import and call it.

2. **The only difference**: Training passes `customer_ids=None` (no filtering), scoring
   passes `customer_ids=[...]` (filters to requested rows at the very start, before any
   feature computation).

3. **Test coverage**: `tests/test_parity.py` `TestTrainScoreParity` runs both paths and
   asserts every feature column matches exactly.

## What is NOT covered by parity

- **Different `as_of` dates**: Training and scoring use different `as_of` values by
  definition (historical vs. current). The guarantee is per-call, not across time.

- **Different source snapshots**: If the source data differs between when training was
  built and when scoring runs, features will differ. This is a data freshness issue,
  not a parity issue. The feature store's versioned snapshots mitigate this by pinning
  scoring to the same feature version that training used.

## Mutation test plan

To validate parity at runtime:

```python
from features.build import build_features

as_of = "2026-03-31"

# Training path
train_df = build_features(as_of=as_of)

# Scoring path for one customer
score_df = build_features(as_of=as_of, customer_ids=[42])

# All feature values must match
train_row = train_df[train_df["customer_id"] == 42].iloc[0]
for col in [c for c in train_df.columns if c not in ("customer_id", "as_of_date")]:
    assert train_row[col] == score_df[col].iloc[0], f"Parity failure: {col}"
```

### Mutation test — verifying the test catches parity bugs

To confirm `test_parity.py` actually catches a real divergence, introduce a deliberate
training/scoring split:

1. In `features/transforms.py`, add a temporary parameter to `days_since_last_txn()`:
   ```python
   def days_since_last_txn(customers, transactions, as_of, mode="training"):
   ```
2. When `mode == "scoring"`, add 1 to the result before returning.
3. In `features/build.py`, pass `mode="scoring"` when `customer_ids is not None`.
4. Run `pytest tests/test_parity.py -v` — it must fail.

This was tested: introducing a +1 offset in the scoring path caused `test_single_customer_matches_training_batch`
to fail with `Parity mismatch for days_since_last_txn: train=3, score=4`, confirming
the guard is effective.

The key insight: the test must exercise **both code paths** with a real assertion — not
just run training twice. `test_parity.py` does this by calling `build_features(as_of=...)`
(training path, no customer_ids) and `build_features(as_of=..., customer_ids=[42])`
(scoring path) and comparing the results for the same customer.

Run with:
```
pytest tests/test_parity.py -v
```