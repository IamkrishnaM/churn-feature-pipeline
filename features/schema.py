"""
Versioned output feature schema: the authoritative list of every feature this pipeline
produces, with dtype, nullability, source(s), and feature-set version.
"""

from dataclasses import dataclass


@dataclass
class FeatureSpec:
    name: str
    dtype: str
    nullable: bool
    source: str
    feature_set_version: str


# Each feature has nullable=False because zero-activity defaults are always applied.
FEATURE_SET_VERSION = "1.0.0"

FEATURE_SCHEMA: list[FeatureSpec] = [
    FeatureSpec(
        name="days_since_last_txn",
        dtype="int64",
        nullable=False,
        source="data/transactions.db",
        feature_set_version=FEATURE_SET_VERSION,
    ),
    FeatureSpec(
        name="txn_count_last_90d",
        dtype="int64",
        nullable=False,
        source="data/transactions.db",
        feature_set_version=FEATURE_SET_VERSION,
    ),
    FeatureSpec(
        name="txn_count_last_30d",
        dtype="int64",
        nullable=False,
        source="data/transactions.db",
        feature_set_version=FEATURE_SET_VERSION,
    ),
    FeatureSpec(
        name="recent_spend_adjusted_90d",
        dtype="float64",
        nullable=False,
        source="data/transactions.db",
        feature_set_version=FEATURE_SET_VERSION,
    ),
    FeatureSpec(
        name="recent_spend_adjusted_30d",
        dtype="float64",
        nullable=False,
        source="data/transactions.db",
        feature_set_version=FEATURE_SET_VERSION,
    ),
    FeatureSpec(
        name="active_months_last_12m",
        dtype="int64",
        nullable=False,
        source="data/transactions_monthly_agg.parquet",
        feature_set_version=FEATURE_SET_VERSION,
    ),
    FeatureSpec(
        name="return_rate_90d",
        dtype="float64",
        nullable=False,
        source="data/transactions.db",
        feature_set_version=FEATURE_SET_VERSION,
    ),
    FeatureSpec(
        name="tenure_days",
        dtype="int64",
        nullable=False,
        source="data/customers.csv",
        feature_set_version=FEATURE_SET_VERSION,
    ),
    FeatureSpec(
        name="channel_organic",
        dtype="int64",
        nullable=False,
        source="data/customers.csv",
        feature_set_version=FEATURE_SET_VERSION,
    ),
    FeatureSpec(
        name="channel_paid_search",
        dtype="int64",
        nullable=False,
        source="data/customers.csv",
        feature_set_version=FEATURE_SET_VERSION,
    ),
    FeatureSpec(
        name="channel_referral",
        dtype="int64",
        nullable=False,
        source="data/customers.csv",
        feature_set_version=FEATURE_SET_VERSION,
    ),
    FeatureSpec(
        name="channel_social",
        dtype="int64",
        nullable=False,
        source="data/customers.csv",
        feature_set_version=FEATURE_SET_VERSION,
    ),
    FeatureSpec(
        name="region_east",
        dtype="int64",
        nullable=False,
        source="data/customers.csv",
        feature_set_version=FEATURE_SET_VERSION,
    ),
    FeatureSpec(
        name="region_north",
        dtype="int64",
        nullable=False,
        source="data/customers.csv",
        feature_set_version=FEATURE_SET_VERSION,
    ),
    FeatureSpec(
        name="region_south",
        dtype="int64",
        nullable=False,
        source="data/customers.csv",
        feature_set_version=FEATURE_SET_VERSION,
    ),
    FeatureSpec(
        name="region_west",
        dtype="int64",
        nullable=False,
        source="data/customers.csv",
        feature_set_version=FEATURE_SET_VERSION,
    ),
    FeatureSpec(
        name="days_to_first_purchase",
        dtype="int64",
        nullable=False,
        source="data/transactions.db + data/customers.csv",
        feature_set_version=FEATURE_SET_VERSION,
    ),
    FeatureSpec(
        name="category_entropy_last_90d",
        dtype="float64",
        nullable=False,
        source="data/transactions.db",
        feature_set_version=FEATURE_SET_VERSION,
    ),
]