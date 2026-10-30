"""
The ONE shared feature-build entry point. Both `scripts/build_training_features.py`
(training path: a historical as-of date, batch of many customers) and
`scripts/score_customer.py` (scoring path: single customer_id, same as-of date) must call
this same function — that is the entire train/score parity guarantee for this pipeline.

There must be exactly one code path here. If you find yourself writing separate logic for
"training mode" vs. "scoring mode" beyond which rows they select at the end, that is a
parity bug — go back and unify it rather than special-casing either path.
"""

import pandas as pd

from features import ingest, transforms
from features.schema import FEATURE_SCHEMA


def build_features(
    as_of: str,
    source_paths: dict | None = None,
    customer_ids: list[int] | None = None,
) -> pd.DataFrame:
    """Build the full feature set as of `as_of` for either the whole customer base
    (training path, `customer_ids=None`) or a specific subset (scoring path, one or more
    `customer_ids`).

    Parameters
    ----------
    as_of : str
        ISO-8601 date string. All features are computed relative to this date.
    source_paths : dict, optional
        Dict with keys 'customers', 'transactions', 'monthly_agg' mapping to file paths.
        Defaults to the standard data/ locations.
    customer_ids : list of int, optional
        If provided, only these customers are included. Training uses None (all customers).

    Returns
    -------
    pd.DataFrame
        One row per requested customer_id, with columns: customer_id, as_of_date,
        and one column per feature from feature_spec.md.
    """
    if source_paths is None:
        source_paths = {
            "customers": "data/customers.csv",
            "transactions": "data/transactions.db",
            "monthly_agg": "data/transactions_monthly_agg.parquet",
        }

    as_of_ts = pd.Timestamp(as_of)

    # ── Load all sources ──────────────────────────────────────────────────
    customers = ingest.load_customers(source_paths["customers"])
    transactions = ingest.load_transactions(source_paths["transactions"])
    monthly_agg = ingest.load_monthly_agg(source_paths["monthly_agg"])

    # ── Filter to requested customer_ids (the ONLY training/scoring difference) ──
    if customer_ids is not None:
        customers = customers[customers["customer_id"].isin(customer_ids)].copy()
        if customers.empty:
            raise ValueError(
                f"None of the requested customer_ids {customer_ids} were found."
            )

    # ── Compute all features ───────────────────────────────────────────────
    features_list = []

    # Recency
    features_list.append(
        transforms.days_since_last_txn(customers, transactions, as_of_ts)
        .rename("days_since_last_txn")
    )

    # Frequency — 90d
    features_list.append(
        transforms.txn_count_last_Nd(customers, transactions, as_of_ts, window_days=90)
        .rename("txn_count_last_90d")
    )

    # Frequency — 30d
    features_list.append(
        transforms.txn_count_last_Nd(customers, transactions, as_of_ts, window_days=30)
        .rename("txn_count_last_30d")
    )

    # Monetary — 90d (v1: multiplier=0.5)
    features_list.append(
        transforms.recent_spend_adjusted_Nd(
            customers, transactions, as_of_ts, window_days=90, return_penalty_multiplier=0.5
        ).rename("recent_spend_adjusted_90d")
    )

    # Monetary — 90d (v2: multiplier=0.75 — same window, higher penalty)
    features_list.append(
        transforms.recent_spend_adjusted_Nd(
            customers, transactions, as_of_ts, window_days=90, return_penalty_multiplier=0.75
        ).rename("recent_spend_adjusted_90d_v2")
    )

    # Monetary — 30d (uses same multiplier 0.5 for first version)
    features_list.append(
        transforms.recent_spend_adjusted_Nd(
            customers, transactions, as_of_ts, window_days=30, return_penalty_multiplier=0.5
        ).rename("recent_spend_adjusted_30d")
    )

    # Engagement breadth
    features_list.append(
        transforms.active_months_last_12m(customers, monthly_agg, as_of_ts)
        .rename("active_months_last_12m")
    )

    # Return rate
    features_list.append(
        transforms.return_rate_90d(customers, transactions, as_of_ts)
        .rename("return_rate_90d")
    )

    # Profile: tenure
    features_list.append(
        transforms.tenure_days(customers, as_of_ts)
        .rename("tenure_days")
    )

    # Profile: channel dummies
    features_list.append(
        transforms.acquisition_channel_dummies(customers)
    )

    # Profile: region dummies
    features_list.append(
        transforms.region_dummies(customers)
    )

    # Days to first purchase
    features_list.append(
        transforms.days_to_first_purchase(customers, transactions, as_of_ts)
        .rename("days_to_first_purchase")
    )

    # Category entropy
    features_list.append(
        transforms.category_entropy_last_90d(customers, transactions, as_of_ts)
        .rename("category_entropy_last_90d")
    )

    # ── Combine into one DataFrame ─────────────────────────────────────────
    features_df = pd.concat(features_list, axis=1).reset_index()
    features_df = features_df.rename(columns={"index": "customer_id"})

    # Add as_of_date column
    features_df["as_of_date"] = as_of_ts

    # Ensure the row count matches what was requested
    expected_count = len(customers)
    assert len(features_df) == expected_count, (
        f"Feature build produced {len(features_df)} rows but expected {expected_count}. "
        "A join may have dropped or duplicated customers."
    )

    return features_df