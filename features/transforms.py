"""
One pure function per candidate feature named in your confirmed `feature_spec.md`.

Each function should:
- Be independent of any I/O (take already-loaded DataFrames in, return a Series/DataFrame out).
- Handle the zero-activity case explicitly, per the default your feature_spec.md states —
  not with a bare try/except that swallows the real problem.
- Only touch the source(s) feature_spec.md names for that feature. If a feature could
  plausibly come from either `transactions.db` or `transactions_monthly_agg.parquet`,
  use the one your spec chose and justified — do not silently blend both.
"""

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Feature 1: Recency
# ---------------------------------------------------------------------------

def days_since_last_txn(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: pd.Timestamp,
) -> pd.Series:
    """Days between `as_of` and the customer's most recent transaction.

    Zero-activity default: full tenure (as_of - signup_date).
    """
    as_of_ts = pd.Timestamp(as_of)

    # Latest transaction per customer
    last_txn = (
        transactions[transactions["txn_timestamp"] <= as_of_ts]
        .groupby("customer_id")["txn_timestamp"]
        .max()
        .reset_index()
    )
    last_txn.columns = ["customer_id", "last_txn_ts"]

    result = customers[["customer_id", "signup_date"]].merge(
        last_txn, on="customer_id", how="left"
    )
    # Compute recency: default to full tenure for zero-activity customers,
    # then overwrite with actual recency for those who have transactions.
    result["recency"] = (as_of_ts - result["signup_date"]).dt.days  # default: tenure
    has_txn = result["last_txn_ts"].notna()
    if has_txn.any():
        result.loc[has_txn, "recency"] = (
            as_of_ts - result.loc[has_txn, "last_txn_ts"]
        ).dt.days
    result = result.set_index("customer_id")["recency"]
    return result


# ---------------------------------------------------------------------------
# Feature 2: Frequency — txn_count_last_Nd
# ---------------------------------------------------------------------------

def txn_count_last_Nd(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: pd.Timestamp,
    window_days: int = 90,
) -> pd.Series:
    """Count of transactions in the trailing N days before as_of.

    Zero-activity default: 0.
    """
    as_of_ts = pd.Timestamp(as_of)
    cutoff = as_of_ts - pd.Timedelta(days=window_days)

    counts = (
        transactions[
            (transactions["txn_timestamp"] >= cutoff)
            & (transactions["txn_timestamp"] <= as_of_ts)
        ]
        .groupby("customer_id")
        .size()
        .reset_index(name="txn_count")
    )

    result = customers[["customer_id"]].merge(
        counts, on="customer_id", how="left"
    )
    result["txn_count"] = result["txn_count"].fillna(0).astype(int)
    result = result.set_index("customer_id")["txn_count"]
    return result


# ---------------------------------------------------------------------------
# Feature 3: Monetary — recent_spend_adjusted_Nd
# ---------------------------------------------------------------------------

def recent_spend_adjusted_Nd(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: pd.Timestamp,
    window_days: int = 90,
    return_penalty_multiplier: float = 0.5,
) -> pd.Series:
    """Sum of amount over trailing N days, with returns penalized.

    Non-return: +amount.  Return: -amount * return_penalty_multiplier.
    Amount is winsorized at the 99th percentile before aggregation.

    Zero-activity default: 0.0.
    """
    as_of_ts = pd.Timestamp(as_of)
    cutoff = as_of_ts - pd.Timedelta(days=window_days)

    # Filter to window first, THEN winsorize so the percentile is computed only
    # on in-window amounts — this avoids leaking future data into the winsorization cap.
    window_txns = transactions[
        (transactions["txn_timestamp"] >= cutoff) & (transactions["txn_timestamp"] <= as_of_ts)
    ].copy()

    if len(window_txns) > 0:
        p99 = window_txns["amount"].quantile(0.99)
        window_txns["amount"] = window_txns["amount"].clip(upper=p99)
    else:
        # For empty windows, still create the column so the rest of the logic works
        window_txns["amount"] = window_txns["amount"]

    # Compute adjusted contribution per transaction
    window_txns["contribution"] = np.where(
        window_txns["is_returned"] == 1,
        -window_txns["amount"] * return_penalty_multiplier,
        window_txns["amount"],
    )

    adjusted = (
        window_txns.groupby("customer_id")["contribution"]
        .sum()
        .reset_index(name="adjusted_spend")
    )

    result = customers[["customer_id"]].merge(
        adjusted, on="customer_id", how="left"
    )
    result["adjusted_spend"] = result["adjusted_spend"].fillna(0.0)
    result = result.set_index("customer_id")["adjusted_spend"]
    return result


# ---------------------------------------------------------------------------
# Feature 4: Engagement Breadth — active_months_last_12m
# ---------------------------------------------------------------------------

def active_months_last_12m(
    customers: pd.DataFrame,
    monthly_agg: pd.DataFrame,
    as_of: pd.Timestamp,
) -> pd.Series:
    """Count of distinct months with txn_count > 0 in the trailing 12 months.

    Zero-activity default: 0.
    """
    as_of_ts = pd.Timestamp(as_of)
    cutoff = as_of_ts - pd.Timedelta(days=365)

    active = monthly_agg[
        (monthly_agg["txn_month"] >= cutoff)
        & (monthly_agg["txn_month"] <= as_of_ts)
        & (monthly_agg["txn_count"] > 0)
    ]

    counts = (
        active.groupby("customer_id")
        .size()
        .reset_index(name="active_months")
    )

    result = customers[["customer_id"]].merge(
        counts, on="customer_id", how="left"
    )
    result["active_months"] = result["active_months"].fillna(0).astype(int)
    result = result.set_index("customer_id")["active_months"]
    return result


# ---------------------------------------------------------------------------
# Feature 5: Return Rate — return_rate_90d
# ---------------------------------------------------------------------------

def return_rate_90d(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: pd.Timestamp,
    window_days: int = 90,
) -> pd.Series:
    """Sum(is_returned) / count(*) over trailing N days.

    Zero-activity default: 0.0.
    """
    as_of_ts = pd.Timestamp(as_of)
    cutoff = as_of_ts - pd.Timedelta(days=window_days)

    window_txns = transactions[
        (transactions["txn_timestamp"] >= cutoff)
        & (transactions["txn_timestamp"] <= as_of_ts)
    ]

    stats = (
        window_txns.groupby("customer_id")
        .agg(txn_count=("amount", "count"), return_count=("is_returned", "sum"))
        .reset_index()
    )
    stats["return_rate"] = np.where(
        stats["txn_count"] > 0, stats["return_count"] / stats["txn_count"], 0.0
    )

    result = customers[["customer_id"]].merge(
        stats[["customer_id", "return_rate"]], on="customer_id", how="left"
    )
    result["return_rate"] = result["return_rate"].fillna(0.0)
    result = result.set_index("customer_id")["return_rate"]
    return result


# ---------------------------------------------------------------------------
# Feature 6: Customer Profile (static)
# ---------------------------------------------------------------------------

def tenure_days(
    customers: pd.DataFrame,
    as_of: pd.Timestamp,
) -> pd.Series:
    """Days between signup_date and as_of."""
    as_of_ts = pd.Timestamp(as_of)
    result = customers[["customer_id", "signup_date"]].copy()
    result["tenure"] = (as_of_ts - result["signup_date"]).dt.days
    result = result.set_index("customer_id")["tenure"]
    return result


def acquisition_channel_dummies(
    customers: pd.DataFrame,
) -> pd.DataFrame:
    """One-hot encoded acquisition_channel columns.

    All expected channels are enforced via categorical dtype so that every
    scoring customer produces the same column set regardless of which channel
    they belong to.
    """
    expected_channels = ["organic", "paid_search", "referral", "social"]
    series = (
        customers[["customer_id", "acquisition_channel"]]
        .set_index("customer_id")["acquisition_channel"]
        .astype(pd.CategoricalDtype(categories=expected_channels))
    )
    dummies = pd.get_dummies(series, prefix="channel").astype(int)
    return dummies


def region_dummies(
    customers: pd.DataFrame,
) -> pd.DataFrame:
    """One-hot encoded region columns.

    All expected regions are enforced via categorical dtype for column-set
    stability between training and scoring.
    """
    expected_regions = ["east", "north", "south", "west"]
    series = (
        customers[["customer_id", "region"]]
        .set_index("customer_id")["region"]
        .astype(pd.CategoricalDtype(categories=expected_regions))
    )
    dummies = pd.get_dummies(series, prefix="region").astype(int)
    return dummies


# ---------------------------------------------------------------------------
# Feature 7: Days to First Purchase
# ---------------------------------------------------------------------------

def days_to_first_purchase(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: pd.Timestamp,
) -> pd.Series:
    """Days between signup_date and the customer's first transaction.

    Zero-activity default: full tenure (as_of - signup_date).
    """
    as_of_ts = pd.Timestamp(as_of)

    first_txn = (
        transactions[transactions["txn_timestamp"] <= as_of_ts]
        .groupby("customer_id")["txn_timestamp"]
        .min()
        .reset_index()
    )
    first_txn.columns = ["customer_id", "first_txn_ts"]

    result = customers[["customer_id", "signup_date"]].merge(
        first_txn, on="customer_id", how="left"
    )
    # Default: full tenure for zero-activity customers. Then overwrite
    # for customers who have at least one transaction.
    has_txn = result["first_txn_ts"].notna()
    result["days_to_first"] = (as_of_ts - result["signup_date"]).dt.days
    if has_txn.any():
        result.loc[has_txn, "days_to_first"] = (
            result.loc[has_txn, "first_txn_ts"] - result.loc[has_txn, "signup_date"]
        ).dt.days
    result = result.set_index("customer_id")["days_to_first"]
    return result


# ---------------------------------------------------------------------------
# Feature 8: Category Entropy — category_entropy_last_90d
# ---------------------------------------------------------------------------

def category_entropy_last_90d(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: pd.Timestamp,
    window_days: int = 90,
) -> pd.Series:
    """Shannon entropy over the category distribution in the trailing N days.

    Entropy = -Σ(p_c * log2(p_c)). Range: 0 (one category) to log2(6) ≈ 2.58.

    Zero-activity default: 0.0.
    """
    as_of_ts = pd.Timestamp(as_of)
    cutoff = as_of_ts - pd.Timedelta(days=window_days)

    window_txns = transactions[
        (transactions["txn_timestamp"] >= cutoff)
        & (transactions["txn_timestamp"] <= as_of_ts)
    ]

    # Per-customer, per-category counts
    counts = (
        window_txns.groupby(["customer_id", "category"])
        .size()
        .reset_index(name="count")
    )

    def _entropy(group: pd.Series) -> float:
        total = group.sum()
        if total == 0:
            return 0.0
        ps = group / total
        return float(-(ps * np.log2(ps)).sum())

    entropies = (
        counts.groupby("customer_id")["count"]
        .apply(_entropy)
        .reset_index(name="entropy")
    )

    result = customers[["customer_id"]].merge(
        entropies, on="customer_id", how="left"
    )
    result["entropy"] = result["entropy"].fillna(0.0)
    result = result.set_index("customer_id")["entropy"]
    return result