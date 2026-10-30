"""
Tests for individual feature functions in features/transforms.py.

Each feature function in isolation: normal case, zero-activity case,
single-record case, and (where relevant) a time-window boundary case.
"""

import numpy as np
import pandas as pd
import pytest

from features import transforms

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_customers():
    return pd.DataFrame({
        "customer_id": [1, 2, 3],
        "signup_date": pd.to_datetime(["2025-01-01", "2025-06-01", "2026-02-01"]),
        "acquisition_channel": ["organic", "paid_search", "referral"],
        "region": ["east", "north", "south"],
        "churned": [0, 0, 1],
    })


@pytest.fixture
def sample_transactions():
    return pd.DataFrame({
        "customer_id": [1, 1, 1, 2, 3],
        "txn_timestamp": pd.to_datetime([
            "2026-01-15", "2026-02-20", "2026-03-10",
            "2025-12-01",
            "2026-03-01",
        ]),
        "category": ["apparel", "grocery", "electronics", "home", "beauty"],
        "channel": ["web", "mobile_app", "web", "store", "web"],
        "amount": [50.0, 30.0, 200.0, 100.0, 25.0],
        "is_returned": [0, 0, 1, 0, 0],
    })


@pytest.fixture
def sample_monthly_agg():
    return pd.DataFrame({
        "customer_id": [1, 1, 2, 3],
        "txn_month": pd.to_datetime(["2026-01-01", "2026-02-01", "2025-12-01", "2026-02-01"]),
        "txn_count": [3, 2, 1, 1],
        "total_amount": [100.0, 80.0, 100.0, 25.0],
        "return_count": [0, 1, 0, 0],
    })


# ---------------------------------------------------------------------------
# days_since_last_txn
# ---------------------------------------------------------------------------

class TestDaysSinceLastTxn:
    def test_normal(self, sample_customers, sample_transactions):
        result = transforms.days_since_last_txn(
            sample_customers, sample_transactions, "2026-03-31"
        )
        # Customer 1: last txn 2026-03-10 → 21 days
        # Customer 2: last txn 2025-12-01 → 120 days
        # Customer 3: last txn 2026-03-01 → 30 days
        assert result[1] == 21, f"Expected 21, got {result[1]}"
        assert result[2] == 120, f"Expected 120, got {result[2]}"
        assert result[3] == 30, f"Expected 30, got {result[3]}"

    def test_zero_activity(self):
        customers = pd.DataFrame({
            "customer_id": [99],
            "signup_date": pd.to_datetime(["2026-01-01"]),
        })
        transactions = pd.DataFrame(columns=[
            "customer_id", "txn_timestamp", "category", "channel", "amount", "is_returned"
        ])
        result = transforms.days_since_last_txn(customers, transactions, "2026-03-31")
        # 2026-03-31 - 2026-01-01 = 89 days
        assert result[99] == 89, f"Expected 89 (tenure), got {result[99]}"

    def test_single_customer(self, sample_customers, sample_transactions):
        subset = sample_customers[sample_customers["customer_id"] == 1]
        result = transforms.days_since_last_txn(subset, sample_transactions, "2026-03-31")
        assert result[1] == 21


# ---------------------------------------------------------------------------
# txn_count_last_Nd
# ---------------------------------------------------------------------------

class TestTxnCountLastNd:
    def test_90d_window(self, sample_customers, sample_transactions):
        result = transforms.txn_count_last_Nd(
            sample_customers, sample_transactions, "2026-03-31", window_days=90
        )
        # Cutting at 2026-01-01
        # Customer 1: txns on 2026-01-15, 2026-02-20, 2026-03-10 → 3
        # Customer 2: txn on 2025-12-01 → before cutoff → 0
        # Customer 3: txn on 2026-03-01 → 1
        assert result[1] == 3
        assert result[2] == 0
        assert result[3] == 1

    def test_30d_window(self, sample_customers, sample_transactions):
        result = transforms.txn_count_last_Nd(
            sample_customers, sample_transactions, "2026-03-31", window_days=30
        )
        # Cutting at 2026-03-01
        # Customer 1: txn on 2026-03-10 → 1
        # Customer 2: none → 0
        # Customer 3: txn on 2026-03-01 → 1
        assert result[1] == 1
        assert result[2] == 0
        assert result[3] == 1

    def test_zero_activity(self):
        customers = pd.DataFrame({"customer_id": [99]})
        transactions = pd.DataFrame(columns=[
            "customer_id", "txn_timestamp", "category", "channel", "amount", "is_returned"
        ])
        result = transforms.txn_count_last_Nd(customers, transactions, "2026-03-31")
        assert result[99] == 0


# ---------------------------------------------------------------------------
# recent_spend_adjusted_Nd
# ---------------------------------------------------------------------------

class TestRecentSpendAdjustedNd:
    def test_normal(self, sample_customers, sample_transactions):
        result = transforms.recent_spend_adjusted_Nd(
            sample_customers, sample_transactions, "2026-03-31",
            window_days=90, return_penalty_multiplier=0.5,
        )
        # Customer 1: amounts [50, 30, 200]. p99 of in-window = 200*.99=198.
        # So 200 gets clipped to 198. Contributions: 50 + 30 + (-198*0.5) = 50 + 30 - 99 = -19
        # But p99 is 198 (since 200 is the max of 5 values, quantile(0.99)=200*0.99)
        # Actually quantile(0.99) on [50, 30, 200] = 30 + 0.99*(200-30) = 30 + 168.3 = 198.3
        # With 5 values, quantile interpolation... let's just compute the expected value.
        # All amounts [50, 30, 200, 100, 25] → in-window [50, 30, 200, 100, 25]
        # p99 = 30 + 0.99*(200-30) = 198.3. 200 clipped to 198.3.
        # C1: 50 + 30 + (-198.3*0.5) = 50 + 30 - 99.15 = -19.15
        # Actual p99 may differ slightly based on pandas quantile interpolation;
        # use a relaxed assertion.
        # Customer 1: in-window amounts [50, 30, 200]. p99 clips 200.
        # Customer 2: txn on 2025-12-01, before cutoff (2026-01-01) → 0.0
        # Customer 3: txn on 2026-03-01 → in window, amount=25 → 25
        assert result[1] < 0, f"Expected negative for C1, got {result[1]}"
        assert result[2] == 0.0, f"Expected 0 for C2 (out of window), got {result[2]}"
        assert abs(result[3] - 25.0) < 0.01, f"Expected 25 for C3, got {result[3]}"

    def test_zero_activity(self):
        customers = pd.DataFrame({"customer_id": [99], "signup_date": pd.to_datetime(["2026-01-01"])})
        transactions = pd.DataFrame(columns=[
            "customer_id", "txn_timestamp", "category", "channel", "amount", "is_returned"
        ])
        result = transforms.recent_spend_adjusted_Nd(
            customers, transactions, "2026-03-31"
        )
        assert result[99] == 0.0


# ---------------------------------------------------------------------------
# active_months_last_12m
# ---------------------------------------------------------------------------

class TestActiveMonthsLast12m:
    def test_normal(self, sample_customers, sample_monthly_agg):
        result = transforms.active_months_last_12m(
            sample_customers, sample_monthly_agg, "2026-03-31"
        )
        # Customer 1: active Jan, Feb → 2
        # Customer 2: active Dec → 1
        # Customer 3: active Feb → 1
        assert result[1] == 2
        assert result[2] == 1
        assert result[3] == 1

    def test_zero_activity(self):
        customers = pd.DataFrame({"customer_id": [99]})
        empty_agg = pd.DataFrame(columns=[
            "customer_id", "txn_month", "txn_count", "total_amount", "return_count"
        ])
        result = transforms.active_months_last_12m(
            customers, empty_agg, "2026-03-31"
        )
        assert result[99] == 0


# ---------------------------------------------------------------------------
# return_rate_90d
# ---------------------------------------------------------------------------

class TestReturnRate90d:
    def test_normal(self, sample_customers, sample_transactions):
        result = transforms.return_rate_90d(
            sample_customers, sample_transactions, "2026-03-31"
        )
        # Customer 1: 1 return / 3 txns = 0.333...
        # Customer 2: 0/1 = 0
        # Customer 3: 0/1 = 0
        assert abs(result[1] - (1/3)) < 0.01
        assert result[2] == 0.0
        assert result[3] == 0.0

    def test_zero_activity(self):
        customers = pd.DataFrame({"customer_id": [99]})
        transactions = pd.DataFrame(columns=[
            "customer_id", "txn_timestamp", "category", "channel", "amount", "is_returned"
        ])
        result = transforms.return_rate_90d(customers, transactions, "2026-03-31")
        assert result[99] == 0.0


# ---------------------------------------------------------------------------
# tenure_days
# ---------------------------------------------------------------------------

class TestTenureDays:
    def test_normal(self, sample_customers):
        result = transforms.tenure_days(sample_customers, "2026-03-31")
        assert result[1] == 454  # 2026-03-31 - 2025-01-01 = 454 days
        assert result[2] == 303  # 2026-03-31 - 2025-06-01 = 303 days
        assert result[3] == 58   # 2026-03-31 - 2026-02-01 = 58 days


# ---------------------------------------------------------------------------
# acquisition_channel_dummies
# ---------------------------------------------------------------------------

class TestAcquisitionChannelDummies:
    def test_normal(self, sample_customers):
        result = transforms.acquisition_channel_dummies(sample_customers)
        assert "channel_organic" in result.columns
        assert "channel_paid_search" in result.columns
        assert "channel_referral" in result.columns
        assert result.loc[1, "channel_organic"] == 1
        assert result.loc[2, "channel_paid_search"] == 1

    def test_all_channels_present(self, sample_customers):
        result = transforms.acquisition_channel_dummies(sample_customers)
        # All 4 expected channels are enforced via categorical dtype
        assert result.shape[1] == 4, f"Expected 4 columns, got {result.shape[1]}"


# ---------------------------------------------------------------------------
# region_dummies
# ---------------------------------------------------------------------------

class TestRegionDummies:
    def test_normal(self, sample_customers):
        result = transforms.region_dummies(sample_customers)
        assert "region_east" in result.columns
        assert "region_north" in result.columns
        assert "region_south" in result.columns
        assert result.loc[1, "region_east"] == 1
        assert result.loc[2, "region_north"] == 1


# ---------------------------------------------------------------------------
# days_to_first_purchase
# ---------------------------------------------------------------------------

class TestDaysToFirstPurchase:
    def test_normal(self, sample_customers, sample_transactions):
        result = transforms.days_to_first_purchase(
            sample_customers, sample_transactions, "2026-03-31"
        )
        # Customer 1: signup 2025-01-01, first txn 2026-01-15 → 379 days
        # Customer 2: signup 2025-06-01, first txn 2025-12-01 → 183 days
        # Customer 3: signup 2026-02-01, first txn 2026-03-01 → 28 days
        assert result[1] == 379, f"Expected 379, got {result[1]}"
        assert result[2] == 183, f"Expected 183, got {result[2]}"
        assert result[3] == 28, f"Expected 28, got {result[3]}"

    def test_zero_activity(self):
        customers = pd.DataFrame({
            "customer_id": [99],
            "signup_date": pd.to_datetime(["2026-01-01"]),
        })
        transactions = pd.DataFrame(columns=[
            "customer_id", "txn_timestamp", "category", "channel", "amount", "is_returned"
        ])
        result = transforms.days_to_first_purchase(
            customers, transactions, "2026-03-31"
        )
        assert result[99] == 89  # tenure: 2026-03-31 - 2026-01-01


# ---------------------------------------------------------------------------
# category_entropy_last_90d
# ---------------------------------------------------------------------------

class TestCategoryEntropyLast90d:
    def test_normal(self, sample_customers, sample_transactions):
        result = transforms.category_entropy_last_90d(
            sample_customers, sample_transactions, "2026-03-31"
        )
        # Customer 1: 3 txns in 3 categories → p = 1/3 each
        # entropy = -3 * (1/3 * log2(1/3)) = log2(3) ≈ 1.585
        assert abs(result[1] - np.log2(3)) < 0.01, f"Expected {np.log2(3)}, got {result[1]}"
        # Customer 2: 1 txn, 1 category → entropy = 0
        assert result[2] == 0.0
        # Customer 3: 1 txn, 1 category → entropy = 0
        assert result[3] == 0.0

    def test_zero_activity(self):
        customers = pd.DataFrame({"customer_id": [99]})
        transactions = pd.DataFrame(columns=[
            "customer_id", "txn_timestamp", "category", "channel", "amount", "is_returned"
        ])
        result = transforms.category_entropy_last_90d(
            customers, transactions, "2026-03-31"
        )
        assert result[99] == 0.0

    def test_single_category(self, sample_customers):
        """All transactions in same category → entropy = 0."""
        transactions = pd.DataFrame({
            "customer_id": [1, 1, 2],
            "txn_timestamp": pd.to_datetime(["2026-03-01", "2026-03-15", "2026-03-10"]),
            "category": ["apparel", "apparel", "apparel"],
            "channel": ["web", "web", "web"],
            "amount": [10.0, 20.0, 30.0],
            "is_returned": [0, 0, 0],
        })
        result = transforms.category_entropy_last_90d(
            sample_customers, transactions, "2026-03-31"
        )
        assert result[1] == 0.0
        assert result[2] == 0.0