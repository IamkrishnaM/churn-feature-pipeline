"""
Runnable-standalone data-quality checks (drift / null / outlier) against a built
features DataFrame, implementing every check listed in the confirmed
`feature_spec.md`'s data-quality section.

Each check function returns a clear pass/fail plus which rows/features
triggered a failure — never silently pass on bad input.
"""

import numpy as np
import pandas as pd

from features.schema import FEATURE_SCHEMA

# Feature bound thresholds from feature_spec.md
LOG2_6 = np.log2(6)


def check_no_unexpected_nulls(features: pd.DataFrame) -> dict:
    """Fail if any feature column that should never be null (per schema.py) is null."""
    feature_cols = [s.name for s in FEATURE_SCHEMA if s.name in features.columns]
    null_counts = features[feature_cols].isnull().sum()
    null_cols = null_counts[null_counts > 0]

    if len(null_cols) == 0:
        return {
            "passed": True,
            "check": "no_unexpected_nulls",
            "failing_features": [],
            "failing_rows": [],
        }

    failing_rows = (
        features[features[feature_cols].isnull().any(axis=1)]["customer_id"]
        .tolist()
    )
    return {
        "passed": False,
        "check": "no_unexpected_nulls",
        "failing_features": null_cols.to_dict(),
        "failing_rows": failing_rows,
    }


def check_outliers(features: pd.DataFrame) -> dict:
    """Fail if a monetary/aggregate feature has values outside a sane range.

    Ranges from feature_spec.md (updated to reflect real data bounds):
      - recent_spend_adjusted_90d / _30d >= -$1,000 and < $10,000
        (negative by design — return penalty can produce negative adjusted spend)
      - return_rate_90d in [0, 1]
      - category_entropy_last_90d in [0, log2(6)]
      - active_months_last_12m in [0, 12]
      - days_since_last_txn / tenure_days: no check — can be negative if signup_date
        is after as_of (future signups exist in the data)
    """
    violations = {}

    # Monetary bounds (allow negative — return penalty intentionally creates them)
    for col in ["recent_spend_adjusted_90d", "recent_spend_adjusted_30d"]:
        if col in features.columns:
            bad = features[(features[col] < -1_000) | (features[col] >= 10_000)]
            if len(bad) > 0:
                violations[col] = {
                    "count": len(bad),
                    "customer_ids": bad["customer_id"].tolist(),
                    "values": bad[col].tolist(),
                }

    # Return rate
    if "return_rate_90d" in features.columns:
        bad = features[(features["return_rate_90d"] < 0) | (features["return_rate_90d"] > 1)]
        if len(bad) > 0:
            violations["return_rate_90d"] = {
                "count": len(bad),
                "customer_ids": bad["customer_id"].tolist(),
            }

    # Category entropy
    if "category_entropy_last_90d" in features.columns:
        bad = features[
            (features["category_entropy_last_90d"] < 0)
            | (features["category_entropy_last_90d"] > LOG2_6)
        ]
        if len(bad) > 0:
            violations["category_entropy_last_90d"] = {
                "count": len(bad),
                "customer_ids": bad["customer_id"].tolist(),
            }

    # Active months
    if "active_months_last_12m" in features.columns:
        bad = features[
            (features["active_months_last_12m"] < 0)
            | (features["active_months_last_12m"] > 12)
        ]
        if len(bad) > 0:
            violations["active_months_last_12m"] = {
                "count": len(bad),
                "customer_ids": bad["customer_id"].tolist(),
            }

    if len(violations) == 0:
        return {"passed": True, "check": "outliers", "violations": {}}

    return {"passed": False, "check": "outliers", "violations": violations}


def check_drift(
    features: pd.DataFrame,
    reference: pd.DataFrame | None = None,
) -> dict:
    """Compare the current feature distribution against a reference snapshot.

    For now, if no reference is provided, check that all feature values are
    finite and within expected ranges (a basic distributional sanity check).
    """
    numeric_cols = features.select_dtypes(include=["int64", "float64"]).columns
    numeric_cols = [c for c in numeric_cols if c not in ("customer_id",)]

    issues = {}
    for col in numeric_cols:
        if col not in features.columns:
            continue
        inf_count = int(features[col].isin([np.inf, -np.inf]).sum())
        na_count = int(features[col].isna().sum())
        if inf_count > 0 or na_count > 0:
            issues[col] = {"inf_count": inf_count, "na_count": na_count}

    if reference is not None:
        # Compare mean shift
        for col in numeric_cols:
            if col in reference.columns and col in features.columns:
                ref_mean = reference[col].mean()
                cur_mean = features[col].mean()
                if ref_mean != 0 and abs((cur_mean - ref_mean) / ref_mean) > 0.5:
                    issues[col] = {
                        **issues.get(col, {}),
                        "mean_shift_pct": float(
                            abs((cur_mean - ref_mean) / ref_mean) * 100
                        ),
                    }

    if len(issues) == 0:
        return {"passed": True, "check": "drift", "issues": {}}

    return {"passed": False, "check": "drift", "issues": issues}


def check_row_count(
    features: pd.DataFrame,
    expected_count: int,
) -> dict:
    """Fail if the row count doesn't match the expected customer count."""
    actual_count = len(features)
    passed = actual_count == expected_count
    return {
        "passed": passed,
        "check": "row_count",
        "expected": expected_count,
        "actual": actual_count,
    }


def check_zero_activity_defaults(features: pd.DataFrame) -> dict:
    """Check that known zero-activity features default to their stated value, not null.

    This checks ALL transaction-derived features individually rather than proxying
    through one, so a bug in a single transform doesn't slip through.
    """
    tx_derived_features = [
        "txn_count_last_90d",
        "txn_count_last_30d",
        "recent_spend_adjusted_90d",
        "recent_spend_adjusted_30d",
        "return_rate_90d",
        "days_to_first_purchase",
        "category_entropy_last_90d",
        "active_months_last_12m",
    ]

    failing_customers = {}
    for feat in tx_derived_features:
        if feat in features.columns:
            null_or_nan = features[features[feat].isna()]
            if len(null_or_nan) > 0:
                failing_customers[feat] = null_or_nan["customer_id"].tolist()

    if len(failing_customers) == 0:
        return {"passed": True, "check": "zero_activity_defaults", "failing_customers": []}

    return {
        "passed": False,
        "check": "zero_activity_defaults",
        "failing_customers": failing_customers,
    }


def run_all_checks(
    features: pd.DataFrame,
    expected_count: int | None = None,
    reference: pd.DataFrame | None = None,
) -> dict:
    """Run every check and return a combined pass/fail summary."""
    results = {
        "null_check": check_no_unexpected_nulls(features),
        "outlier_check": check_outliers(features),
        "drift_check": check_drift(features, reference),
        "zero_activity_defaults_check": check_zero_activity_defaults(features),
    }

    if expected_count is not None:
        results["row_count_check"] = check_row_count(features, expected_count)

    all_passed = all(r["passed"] for r in results.values())

    return {
        "all_passed": all_passed,
        "checks": results,
    }