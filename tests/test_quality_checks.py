"""
Tests for data-quality checks in features/quality_checks.py.

Feed each check a deliberately bad input and confirm it fires;
feed it clean input and confirm it doesn't false-positive.
"""

import numpy as np
import pandas as pd
import pytest

from features import quality_checks as qc


@pytest.fixture
def clean_features():
    """A clean features DataFrame with all values within expected ranges."""
    n = 10
    np.random.seed(42)
    df = pd.DataFrame({
        "customer_id": range(1, n + 1),
        "days_since_last_txn": np.random.randint(0, 365, n).tolist(),
        "txn_count_last_90d": np.random.randint(0, 50, n).tolist(),
        "txn_count_last_30d": np.random.randint(0, 20, n).tolist(),
        "recent_spend_adjusted_90d": np.random.uniform(0, 5000, n).tolist(),
        "recent_spend_adjusted_30d": np.random.uniform(0, 2000, n).tolist(),
        "active_months_last_12m": np.random.randint(0, 12, n).tolist(),
        "return_rate_90d": np.random.uniform(0, 1, n).tolist(),
        "tenure_days": np.random.randint(30, 800, n).tolist(),
        "days_to_first_purchase": np.random.randint(0, 365, n).tolist(),
        "category_entropy_last_90d": np.random.uniform(0, 2.58, n).tolist(),
        "channel_organic": np.random.randint(0, 2, n).tolist(),
        "channel_paid_search": np.random.randint(0, 2, n).tolist(),
        "channel_referral": np.random.randint(0, 2, n).tolist(),
        "channel_social": np.random.randint(0, 2, n).tolist(),
        "region_east": np.random.randint(0, 2, n).tolist(),
        "region_north": np.random.randint(0, 2, n).tolist(),
        "region_south": np.random.randint(0, 2, n).tolist(),
        "region_west": np.random.randint(0, 2, n).tolist(),
    })
    return df


# ---------------------------------------------------------------------------
# check_no_unexpected_nulls
# ---------------------------------------------------------------------------

class TestNoUnexpectedNulls:
    def test_clean_passes(self, clean_features):
        result = qc.check_no_unexpected_nulls(clean_features)
        assert result["passed"] is True

    def test_null_triggers_failure(self, clean_features):
        bad = clean_features.copy()
        bad.loc[0, "txn_count_last_90d"] = np.nan
        result = qc.check_no_unexpected_nulls(bad)
        assert result["passed"] is False
        assert "txn_count_last_90d" in result["failing_features"]

    def test_multiple_nulls_detected(self, clean_features):
        bad = clean_features.copy()
        bad.loc[0, "recent_spend_adjusted_90d"] = np.nan
        bad.loc[1, "tenure_days"] = np.nan
        result = qc.check_no_unexpected_nulls(bad)
        assert result["passed"] is False
        assert len(result["failing_features"]) == 2


# ---------------------------------------------------------------------------
# check_outliers
# ---------------------------------------------------------------------------

class TestOutliers:
    def test_clean_passes(self, clean_features):
        result = qc.check_outliers(clean_features)
        assert result["passed"] is True

    def test_mild_negative_spend_passes(self, clean_features):
        """Return penalty can produce negative spend; -$100 is within the sane range."""
        bad = clean_features.copy()
        bad.loc[0, "recent_spend_adjusted_90d"] = -100.0
        result = qc.check_outliers(bad)
        assert result["passed"] is True, "Mild negative spend should pass (return penalty)"

    def test_extreme_negative_spend_triggers(self, clean_features):
        bad = clean_features.copy()
        bad.loc[0, "recent_spend_adjusted_90d"] = -5_000.0
        result = qc.check_outliers(bad)
        assert result["passed"] is False

    def test_excessive_spend_triggers(self, clean_features):
        bad = clean_features.copy()
        bad.loc[0, "recent_spend_adjusted_90d"] = 50_000.0
        result = qc.check_outliers(bad)
        assert result["passed"] is False

    def test_return_rate_out_of_range(self, clean_features):
        bad = clean_features.copy()
        bad.loc[0, "return_rate_90d"] = 1.5
        result = qc.check_outliers(bad)
        assert result["passed"] is False

    def test_category_entropy_out_of_range(self, clean_features):
        bad = clean_features.copy()
        bad.loc[0, "category_entropy_last_90d"] = 5.0
        result = qc.check_outliers(bad)
        assert result["passed"] is False

    def test_active_months_out_of_range(self, clean_features):
        bad = clean_features.copy()
        bad.loc[0, "active_months_last_12m"] = 15
        result = qc.check_outliers(bad)
        assert result["passed"] is False


# ---------------------------------------------------------------------------
# check_zero_activity_defaults
# ---------------------------------------------------------------------------

class TestZeroActivityDefaults:
    def test_clean_passes(self, clean_features):
        result = qc.check_zero_activity_defaults(clean_features)
        assert result["passed"] is True

    def test_null_txn_count_triggers(self, clean_features):
        bad = clean_features.copy()
        bad.loc[0, "txn_count_last_90d"] = np.nan
        result = qc.check_zero_activity_defaults(bad)
        assert result["passed"] is False
        assert "txn_count_last_90d" in result["failing_customers"]
        assert 1 in result["failing_customers"]["txn_count_last_90d"]

    def test_missing_returns_only(self, clean_features):
        """Only return_rate_90d is null — should still fail."""
        bad = clean_features.copy()
        bad.loc[0, "return_rate_90d"] = np.nan
        result = qc.check_zero_activity_defaults(bad)
        assert result["passed"] is False
        assert "return_rate_90d" in result["failing_customers"]


# ---------------------------------------------------------------------------
# check_row_count
# ---------------------------------------------------------------------------

class TestRowCount:
    def test_matching_count_passes(self, clean_features):
        result = qc.check_row_count(clean_features, len(clean_features))
        assert result["passed"] is True

    def test_mismatch_fails(self, clean_features):
        result = qc.check_row_count(clean_features, len(clean_features) + 1)
        assert result["passed"] is False


# ---------------------------------------------------------------------------
# run_all_checks
# ---------------------------------------------------------------------------

class TestRunAllChecks:
    def test_clean_passes(self, clean_features):
        result = qc.run_all_checks(clean_features, expected_count=len(clean_features))
        assert result["all_passed"] is True

    def test_failing_check_propagates(self, clean_features):
        bad = clean_features.copy()
        bad.loc[0, "return_rate_90d"] = 1.5  # outlier
        result = qc.run_all_checks(bad, expected_count=len(bad))
        assert result["all_passed"] is False
        assert result["checks"]["outlier_check"]["passed"] is False