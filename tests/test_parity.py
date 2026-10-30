"""
Train/score parity test: build features for the same customer via the training path
(historical as-of date, batch) and the scoring path (single customer, same as-of date),
and assert the resulting feature values are identical.

If these two paths can't be driven through the same test with the same expected output,
the parity guarantee in the spec isn't real — fix build.py, not the test.
"""

import pandas as pd
import pytest

from features.build import build_features


class TestTrainScoreParity:
    """The core parity guarantee: training-path and scoring-path produce identical features."""

    def test_single_customer_matches_training_batch(self):
        """Feature values for customer 42 built via training (all customers) must match
        values built via scoring (customer_ids=[42]) at the same as-of date."""
        as_of = "2026-03-31"

        # Training path: build for all customers
        train_df = build_features(as_of=as_of)
        train_row = train_df[train_df["customer_id"] == 42]

        assert len(train_row) == 1, f"Customer 42 not found in training output"

        # Scoring path: build for just customer 42
        score_df = build_features(as_of=as_of, customer_ids=[42])

        assert len(score_df) == 1, "Scoring should return exactly 1 row"

        # Compare every feature column (exclude customer_id and as_of_date)
        feature_cols = [c for c in train_df.columns if c not in ("customer_id", "as_of_date")]
        for col in feature_cols:
            train_val = train_row[col].iloc[0]
            score_val = score_df[col].iloc[0]

            # Use pandas equality (handles NaN, dtype differences)
            if pd.isna(train_val) and pd.isna(score_val):
                continue  # both NaN — not a parity issue

            if isinstance(train_val, float) or isinstance(score_val, float):
                assert abs(float(train_val) - float(score_val)) < 0.001, (
                    f"Parity mismatch for {col}: train={train_val}, score={score_val}"
                )
            else:
                assert train_val == score_val, (
                    f"Parity mismatch for {col}: train={train_val}, score={score_val}"
                )

    def test_multiple_customers_match_training_batch(self):
        """Scoring multiple customers at once should match batch."""
        as_of = "2026-03-31"
        target_ids = [7, 42, 137, 999]

        train_df = build_features(as_of=as_of)
        score_df = build_features(as_of=as_of, customer_ids=target_ids)

        assert len(score_df) == len(target_ids), (
            f"Expected {len(target_ids)} rows, got {len(score_df)}"
        )

        feature_cols = [c for c in train_df.columns if c not in ("customer_id", "as_of_date")]
        for _, score_row in score_df.iterrows():
            cid = score_row["customer_id"]
            train_row = train_df[train_df["customer_id"] == cid]
            assert len(train_row) == 1, f"Customer {cid} not found in training output"

            for col in feature_cols:
                tv = train_row[col].iloc[0]
                sv = score_row[col]

                if pd.isna(tv) and pd.isna(sv):
                    continue
                if isinstance(tv, float) or isinstance(sv, float):
                    assert abs(float(tv) - float(sv)) < 0.001, (
                        f"Parity mismatch for customer {cid}, {col}: "
                        f"train={tv}, score={sv}"
                    )
                else:
                    assert tv == sv, (
                        f"Parity mismatch for customer {cid}, {col}: "
                        f"train={tv}, score={sv}"
                    )