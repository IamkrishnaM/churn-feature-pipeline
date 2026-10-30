"""
Tests for the feature store in feature_store/store.py.

For each versioned feature from feature_spec.md, register its versions, confirm
each is independently retrievable, confirm is_latest correctly identifies the
highest version, and confirm list_versions returns every version with distinct
parquet_path values that all actually exist on disk.
"""

import os
import pytest

from feature_store import store


class TestFeatureStore:
    """Tests for the local feature store (SQLite registry + parquet values)."""

    def setup_method(self):
        """Ensure a clean registry for each test."""
        # Remove the registry DB if it exists so tests start clean
        if os.path.exists(store.REGISTRY_DB):
            os.remove(store.REGISTRY_DB)

    def _make_version_df(self, feature_name, n_customers=5):
        """Helper to create a plausible version DataFrame."""
        import pandas as pd
        return pd.DataFrame({
            "customer_id": list(range(1, n_customers + 1)),
            feature_name: [float(i * 10) for i in range(1, n_customers + 1)],
            "as_of_date": ["2026-03-31"] * n_customers,
        })

    # ------------------------------------------------------------------
    # Single feature, two versions
    # ------------------------------------------------------------------

    def test_register_and_retrieve_first_version(self):
        """Register v1 of a feature, confirm it's retrievable and is_latest."""
        df = self._make_version_df("test_feature_a")
        v1 = store.register_version(
            feature_name="test_feature_a",
            values_df=df,
            description="Test feature A v1",
            source_columns="test_source.csv:col_a",
            transform_summary="Sum of test col_a over 90 days",
            business_rationale="Testing feature store",
            parameters={"window_days": 90},
        )
        assert v1 == 1, "First version should be v1"

        # Retrieve by version
        retrieved = store.get_version("test_feature_a", 1)
        assert len(retrieved) == 5
        assert "customer_id" in retrieved.columns
        assert "test_feature_a" in retrieved.columns

        # Retrieve latest
        latest = store.get_latest("test_feature_a")
        assert len(latest) == 5

    def test_two_versions_is_latest_correct(self):
        """After registering v2, v2 should be latest and v1 should not."""
        df1 = self._make_version_df("test_feature_b")
        df2 = self._make_version_df("test_feature_b", n_customers=3)

        store.register_version(
            feature_name="test_feature_b",
            values_df=df1,
            description="Feature B v1",
            source_columns="source_b",
            transform_summary="Count",
            business_rationale="Test",
            parameters={"window_days": 90},
        )
        v2 = store.register_version(
            feature_name="test_feature_b",
            values_df=df2,
            description="Feature B v2",
            source_columns="source_b",
            transform_summary="Count with shorter window",
            business_rationale="Shorter window for sensitivity",
            parameters={"window_days": 30},
        )
        assert v2 == 2, "Second version should be v2"

        # get_latest should return v2 (3 customers)
        latest = store.get_latest("test_feature_b")
        assert len(latest) == 3, "v2 should have 3 customers"

        # get_version(1) should still return v1 (5 customers)
        v1_retrieved = store.get_version("test_feature_b", 1)
        assert len(v1_retrieved) == 5, "v1 should still have 5 customers"

    # ------------------------------------------------------------------
    # Two distinct features, each with two versions
    # ------------------------------------------------------------------

    def test_two_features_each_two_versions(self):
        """Two distinct features, each with ≥2 versions, independently retrievable."""
        # Feature A: 2 versions
        df_a1 = self._make_version_df("feature_a", n_customers=4)
        df_a2 = self._make_version_df("feature_a", n_customers=6)

        store.register_version(
            "feature_a", df_a1, "A v1", "src_a", "transform a v1",
            "Rationale A v1", {"param": 90},
        )
        store.register_version(
            "feature_a", df_a2, "A v2", "src_a", "transform a v2",
            "Rationale A v2", {"param": 30},
        )

        # Feature B: 2 versions
        df_b1 = self._make_version_df("feature_b", n_customers=10)
        df_b2 = self._make_version_df("feature_b", n_customers=2)

        store.register_version(
            "feature_b", df_b1, "B v1", "src_b", "transform b v1",
            "Rationale B v1", {"threshold": 0.5},
        )
        v2_b = store.register_version(
            "feature_b", df_b2, "B v2", "src_b", "transform b v2",
            "Rationale B v2", {"threshold": 0.75},
        )
        assert v2_b == 2

        # Confirm independent retrieval
        assert len(store.get_version("feature_a", 1)) == 4
        assert len(store.get_version("feature_a", 2)) == 6
        assert len(store.get_version("feature_b", 1)) == 10
        assert len(store.get_version("feature_b", 2)) == 2

        # Confirm is_latest for each feature
        assert len(store.get_latest("feature_a")) == 6  # v2
        assert len(store.get_latest("feature_b")) == 2  # v2

    # ------------------------------------------------------------------
    # list_versions
    # ------------------------------------------------------------------

    def test_list_versions(self):
        """list_versions returns all versions with distinct parquet paths."""
        df1 = self._make_version_df("list_test")
        df2 = self._make_version_df("list_test", n_customers=7)

        store.register_version(
            "list_test", df1, "v1", "src", "transform",
            "Rationale", {"p": 1},
        )
        store.register_version(
            "list_test", df2, "v2", "src", "transform",
            "Rationale", {"p": 2},
        )

        versions_df = store.list_versions("list_test")
        assert len(versions_df) == 2
        # Most recent first
        assert int(versions_df.iloc[0]["version"]) == 2
        assert int(versions_df.iloc[1]["version"]) == 1

        # Distinct parquet paths that all exist on disk
        paths = versions_df["parquet_path"].tolist()
        assert len(set(paths)) == 2, "parquet_path values must be distinct"
        for p in paths:
            assert os.path.exists(p), f"Parquet file {p} does not exist"

    # ------------------------------------------------------------------
    # Version retrieval for non-existent feature
    # ------------------------------------------------------------------

    def test_get_nonexistent_version_raises(self):
        """Requesting a non-existent version should raise ValueError."""
        with pytest.raises(ValueError, match="not found"):
            store.get_version("nonexistent_feature", 1)

    def test_get_nonexistent_latest_raises(self):
        """Requesting latest for a non-existent feature should raise ValueError."""
        with pytest.raises(ValueError, match="No registered version"):
            store.get_latest("nonexistent_feature")