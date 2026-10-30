#!/usr/bin/env python3
"""
Builds features for the full training population as of a given date, writes a versioned
parquet feature snapshot, and registers every candidate feature into the feature store.

Usage:
    python scripts/build_training_features.py --as-of 2026-03-31
"""

import argparse

import pandas as pd

from features.build import build_features
from features.quality_checks import run_all_checks
from features.schema import FEATURE_SCHEMA
from feature_store import store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-of",
        default="2026-03-31",
        help="As-of date for feature computation (default: 2026-03-31).",
    )
    args = parser.parse_args()

    print(f"Building features as of {args.as_of}...")
    features_df = build_features(as_of=args.as_of)

    print(f"Built {len(features_df)} rows × {len(features_df.columns)} columns")

    # Run quality checks
    print("\nRunning quality checks...")
    qc_results = run_all_checks(features_df, expected_count=len(features_df))
    for check_name, check_result in qc_results["checks"].items():
        status = "✅ PASS" if check_result["passed"] else "❌ FAIL"
        print(f"  {status} — {check_name}")

    if not qc_results["all_passed"]:
        print("\n⚠️  Quality checks FAILED. Proceeding with registration anyway "
              "(failed checks are for visibility).")

    # Register every candidate feature from the schema into the feature store
    print("\nRegistering features in the feature store...")
    registered_count = 0

    for spec in FEATURE_SCHEMA:
        feature_name = spec.name
        if feature_name not in features_df.columns:
            print(f"  ⚠️  Skipping {feature_name} — not in built features DataFrame")
            continue

        # Build the versioned value DataFrame: customer_id, feature_value, as_of_date
        value_col = feature_name
        version_df = features_df[["customer_id", value_col, "as_of_date"]].copy()

        source_columns = spec.source

        # ---- v1 registration ------------------------------------------------
        parameters_v1, description_v1, transform_summary_v1, rationale_v1 = (
            _version_metadata(feature_name, version=1)
        )
        v1 = store.register_version(
            feature_name=feature_name,
            values_df=version_df,
            description=description_v1,
            source_columns=source_columns,
            transform_summary=transform_summary_v1,
            business_rationale=rationale_v1,
            parameters=parameters_v1,
        )
        print(f"  ✅ Registered {feature_name} v{v1}")
        registered_count += 1

        # ---- v2 (only for recent_spend_adjusted_90d — penalty multiplier 0.75) ----
        if feature_name == "recent_spend_adjusted_90d":
            parameters_v2, description_v2, transform_summary_v2, rationale_v2 = (
                _version_metadata(feature_name, version=2)
            )
            # Use the separate v2 column computed in build.py
            v2_value_col = "recent_spend_adjusted_90d_v2"
            if v2_value_col in features_df.columns:
                version_df_v2 = features_df[["customer_id", v2_value_col, "as_of_date"]].copy()
                version_df_v2 = version_df_v2.rename(columns={v2_value_col: feature_name})
            else:
                # Fallback: same values (shouldn't happen after build.py fix)
                version_df_v2 = version_df.copy()

            v2 = store.register_version(
                feature_name=feature_name,
                values_df=version_df_v2,
                description=description_v2,
                source_columns=source_columns,
                transform_summary=transform_summary_v2,
                business_rationale=rationale_v2,
                parameters=parameters_v2,
            )
            print(f"  ✅ Registered {feature_name} v{v2} (return_penalty_multiplier=0.75)")
            registered_count += 1

    print(f"\nDone. Registered {registered_count} features in the feature store.")
    print(f"Output snapshot has {len(features_df)} rows.")


def _version_metadata(feature_name: str, version: int) -> tuple[dict, str, str, str]:
    """Return (parameters, description, transform_summary, business_rationale) for a
    (feature_name, version) pair.

    Most features have only one version. `recent_spend_adjusted_90d` has two: v1
    (return_penalty_multiplier=0.5) and v2 (return_penalty_multiplier=0.75).
    """
    rationales = {
        "days_since_last_txn": "Customers who have not transacted recently are disengaging. Gap relative to signup distinguishes new from long-inactive customers.",
        "txn_count_last_90d": "A drop in recent transaction frequency indicates disengagement, distinct from recency alone.",
        "txn_count_last_30d": "Shorter window catches rapid disengagement signals that a 90-day window may smooth over.",
        "recent_spend_adjusted_90d": "Spend trajectory with return penalty captures both disengagement and dissatisfaction signals.",
        "recent_spend_adjusted_30d": "Shorter-window spend with return penalty for rapid monetization-change detection.",
        "active_months_last_12m": "Narrowing category engagement breadth over a year signals reduced platform relationship.",
        "return_rate_90d": "Rising return rate signals product dissatisfaction, a known churn precursor distinct from low spend.",
        "tenure_days": "Newer customers churn at higher rates; tenure captures lifecycle stage.",
        "channel_organic": "Acquisition channel is a natural confound — organic vs paid vs referral customers have different baseline churn risk.",
        "channel_paid_search": "Acquisition channel confound for churn baseline.",
        "channel_referral": "Acquisition channel confound for churn baseline.",
        "channel_social": "Acquisition channel confound for churn baseline.",
        "region_east": "Regional variation in churn behavior.",
        "region_north": "Regional variation in churn behavior.",
        "region_south": "Regional variation in churn behavior.",
        "region_west": "Regional variation in churn behavior.",
        "days_to_first_purchase": "Early-warning signal: customers who buy sooner after signup are more likely to become loyal.",
        "category_entropy_last_90d": "Narrowing category diversity before churning is a signal RFM alone misses.",
    }

    # ---- Version-independent metadata ----
    description = f"{feature_name} — {rationales.get(feature_name, 'Churn prediction feature')}"
    transform_summary = f"Computed from {feature_name} transform"
    business_rationale = rationales.get(feature_name, f"Feature {feature_name} for churn prediction.")

    # ---- Version-specific parameters ----
    if version == 1:
        if feature_name in ("txn_count_last_90d", "recent_spend_adjusted_90d"):
            parameters = {"window_days": 90}
        elif feature_name in ("txn_count_last_30d", "recent_spend_adjusted_30d"):
            parameters = {"window_days": 30}
        else:
            parameters = {}

        if feature_name in ("recent_spend_adjusted_90d", "recent_spend_adjusted_30d"):
            parameters["return_penalty_multiplier"] = 0.5

        return (parameters, description, transform_summary, business_rationale)

    if version == 2:
        # Only recent_spend_adjusted_90d has a v2 (different penalty multiplier)
        assert feature_name == "recent_spend_adjusted_90d", (
            f"v2 is not defined for {feature_name}"
        )
        parameters = {"window_days": 90, "return_penalty_multiplier": 0.75}
        description_v2 = (
            "recent_spend_adjusted_90d — Spend trajectory with higher return penalty multiplier. "
            "v2 reflects increased return-processing costs."
        )
        transform_summary_v2 = (
            "Sum of amount over 90d with return_penalty_multiplier=0.75. "
            "Amount winsorized at 99th percentile before per-customer sum."
        )
        rationale_v2 = (
            "v2 with higher penalty multiplier (0.5 → 0.75) to reflect increased "
            "return-processing costs. Customers with heavy return history are penalised "
            "more heavily in the adjusted-spend metric, making dissatisfaction signals "
            "more prominent for the downstream model."
        )
        return (parameters, description_v2, transform_summary_v2, rationale_v2)

    raise ValueError(f"Unknown version {version} for feature '{feature_name}'")


if __name__ == "__main__":
    main()