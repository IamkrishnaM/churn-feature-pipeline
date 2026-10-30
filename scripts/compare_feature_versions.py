#!/usr/bin/env python3
"""
Version comparison for versioned features from feature_spec.md.

For each versioned feature, loads all registered versions from the feature store and
reports how many customers' values changed, the distribution shift, and rank-order changes.

Output is written to VERSION_COMPARISON.md.
"""

import numpy as np
import pandas as pd

from feature_store import store

# Versioned feature comparisons required by feature_spec.md
#
# The spec defines three versioning axes; the comparison script must handle
# each one according to how the data is stored:
#
# 1. Same logical feature, different feature_name (window_days 90 vs 30):
#    txn_count_last_90d v1  ↔  txn_count_last_30d v1
#    These are stored under *different* feature_names, each with one version.
#
# 2. Same logical feature, different feature_name (window_days 90 vs 30):
#    recent_spend_adjusted_90d v1  ↔  recent_spend_adjusted_30d v1
#    Same structure as #1.
#
# 3. Same feature_name, different version (same window_days, different multiplier):
#    recent_spend_adjusted_90d v1 (multiplier=0.5)  ↔  recent_spend_adjusted_90d v2 (multiplier=0.75)
#    Stored under the SAME feature_name with two version numbers.

VERSION_COMPARISONS = [
    {
        "label": "Transaction Count — window 90d vs 30d",
        "description": "txn_count_last_90d (v1, window_days=90) vs txn_count_last_30d (v1, window_days=30)",
        "feature_name_v1": "txn_count_last_90d",
        "version_v1": 1,
        "feature_name_v2": "txn_count_last_30d",
        "version_v2": 1,
    },
    {
        "label": "Adjusted Spend — window 90d vs 30d",
        "description": "recent_spend_adjusted_90d (v1, window_days=90, multiplier=0.5) vs recent_spend_adjusted_30d (v1, window_days=30, multiplier=0.5)",
        "feature_name_v1": "recent_spend_adjusted_90d",
        "version_v1": 1,
        "feature_name_v2": "recent_spend_adjusted_30d",
        "version_v2": 1,
    },
    {
        "label": "Adjusted Spend — penalty multiplier 0.5 vs 0.75",
        "description": "recent_spend_adjusted_90d v1 (multiplier=0.5) vs recent_spend_adjusted_90d v2 (multiplier=0.75), same window",
        "feature_name_v1": "recent_spend_adjusted_90d",
        "version_v1": 1,
        "feature_name_v2": "recent_spend_adjusted_90d",
        "version_v2": 2,
    },
]


def _percentile_rank(series: pd.Series) -> pd.Series:
    """Compute percentile rank (0-100) for a series."""
    return series.rank(pct=True) * 100


def _compare_pair(
    label: str,
    description: str,
    feat_name_v1: str,
    version_v1: int,
    feat_name_v2: str,
    version_v2: int,
) -> str:
    """Compare two versions and return a markdown section."""
    lines = []

    try:
        df_v1 = store.get_version(feat_name_v1, version_v1)
        df_v2 = store.get_version(feat_name_v2, version_v2)
    except ValueError:
        return ""

    # Identify value columns (not customer_id or as_of_date)
    value_col_v1 = [c for c in df_v1.columns if c not in ("customer_id", "as_of_date")][0]
    value_col_v2 = [c for c in df_v2.columns if c not in ("customer_id", "as_of_date")][0]

    # Merge on customer_id
    # If both value columns have the same name, suffixes disambiguate.
    # If they differ, the merge keeps the original column names.
    merged = df_v1[["customer_id", value_col_v1]].merge(
        df_v2[["customer_id", value_col_v2]],
        on="customer_id",
        suffixes=("_v1", "_v2"),
    )

    # Resolve the actual column names after merge
    if value_col_v1 == value_col_v2:
        col_v1 = f"{value_col_v1}_v1"
        col_v2 = f"{value_col_v2}_v2"
    else:
        col_v1 = value_col_v1
        col_v2 = value_col_v2

    total_customers = len(merged)
    changed = (merged[col_v1] != merged[col_v2]).sum()
    pct_changed = changed / total_customers * 100 if total_customers > 0 else 0

    v1_vals = merged[col_v1]
    v2_vals = merged[col_v2]

    lines.append(f"## {label}")
    lines.append("")
    lines.append(f"_{description}_")
    lines.append("")
    lines.append(f"**{feat_name_v1} v{version_v1} → {feat_name_v2} v{version_v2}**")
    lines.append("")
    lines.append(f"- **Total customers**: {total_customers}")
    lines.append(f"- **Customers with changed values**: {changed} ({pct_changed:.1f}%)")
    lines.append("")
    lines.append("### Distribution (v1)")
    lines.append(f"- Mean: {v1_vals.mean():.4f}")
    lines.append(f"- Median: {v1_vals.median():.4f}")
    lines.append(f"- Std:  {v1_vals.std():.4f}")
    lines.append(f"- Min:  {v1_vals.min():.4f}")
    lines.append(f"- Max:  {v1_vals.max():.4f}")
    lines.append("")
    lines.append("### Distribution (v2)")
    lines.append(f"- Mean: {v2_vals.mean():.4f}")
    lines.append(f"- Median: {v2_vals.median():.4f}")
    lines.append(f"- Std:  {v2_vals.std():.4f}")
    lines.append(f"- Min:  {v2_vals.min():.4f}")
    lines.append(f"- Max:  {v2_vals.max():.4f}")
    lines.append("")

    if v1_vals.nunique() > 1 and v2_vals.nunique() > 1:
        rank_v1 = _percentile_rank(v1_vals)
        rank_v2 = _percentile_rank(v2_vals)
        rank_corr = rank_v1.corr(rank_v2)
        mean_rank_abs_change = (rank_v1 - rank_v2).abs().mean()
        lines.append("### Rank-Order Change")
        lines.append(f"- Spearman (rank) correlation: {rank_corr:.4f}")
        lines.append(f"- Mean absolute rank-percentile change: {mean_rank_abs_change:.2f}")
        lines.append("")

        try:
            q1_quartile = pd.qcut(rank_v1, 4, labels=[1, 2, 3, 4], duplicates="drop")
            q2_quartile = pd.qcut(rank_v2, 4, labels=[1, 2, 3, 4], duplicates="drop")
            moved_quartile = (q1_quartile != q2_quartile).sum()
            lines.append(f"- Customers crossing quartile boundaries: {moved_quartile} "
                         f"({moved_quartile / total_customers * 100:.1f}%)")
            lines.append("")
        except ValueError:
            pass  # qcut can fail if all values are identical — skip gracefully

    lines.append("### Interpretation")
    if pct_changed < 5:
        lines.append("Few customers changed values — this version change is unlikely "
                     "to materially affect a downstream model.")
    elif pct_changed < 25:
        lines.append("A moderate fraction of customers changed values. The downstream "
                     "model would likely notice this shift for those customers, but the "
                     "overall feature distribution is similar.")
    else:
        lines.append("A substantial fraction of customers changed values. A model "
                     "consuming this feature would likely produce materially different "
                     "predictions for many customers between versions.")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    lines = []
    lines.append("# Version Comparison Report")
    lines.append("")
    lines.append("Comparison of versioned features registered in the feature store, ")
    lines.append("per the versioning table in feature_spec.md.")
    lines.append("")

    for comp in VERSION_COMPARISONS:
        section = _compare_pair(
            label=comp["label"],
            description=comp["description"],
            feat_name_v1=comp["feature_name_v1"],
            version_v1=comp["version_v1"],
            feat_name_v2=comp["feature_name_v2"],
            version_v2=comp["version_v2"],
        )
        if section:
            lines.append(section)

    if len([l for l in lines if l.startswith("## ")]) == 0:
        lines.append("No version comparisons could be computed — the feature store may not "
                     "have all required versions yet.")

    # Write the output
    output = "\n".join(lines)
    with open("VERSION_COMPARISON.md", "w") as f:
        f.write(output)
    print("Written VERSION_COMPARISON.md")


if __name__ == "__main__":
    main()