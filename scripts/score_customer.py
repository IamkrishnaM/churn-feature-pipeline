#!/usr/bin/env python3
"""
Builds features for one or more specific customer_ids as of a given date, using the
scoring path of the same shared build_features(as_of, ...) entry point used by
build_training_features.py.

Usage:
    python scripts/score_customer.py --customer-id 42 --customer-id 137 --as-of 2026-03-31
"""

import argparse

from features.build import build_features


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--customer-id",
        type=int,
        action="append",
        required=True,
        help="Customer ID to score. May be passed multiple times.",
    )
    parser.add_argument(
        "--as-of",
        default="2026-03-31",
        help="As-of date for feature computation (default: 2026-03-31).",
    )
    args = parser.parse_args()

    customer_ids = args.customer_id
    print(f"Scoring features for customer(s) {customer_ids} as of {args.as_of}...")

    try:
        features_df = build_features(
            as_of=args.as_of,
            customer_ids=customer_ids,
        )
    except ValueError as e:
        print(f"Error: {e}")
        return

    print(f"\nFeatures for {len(features_df)} customer(s):")
    print("-" * 80)

    # Display feature values for each customer, transposed for readability
    display_cols = [c for c in features_df.columns if c not in ("as_of_date",)]
    for _, row in features_df.iterrows():
        print(f"\n  Customer ID: {row['customer_id']}")
        print(f"  As-of date:  {row['as_of_date']}")
        print(f"  {'─' * 40}")
        for col in display_cols:
            if col != "customer_id":
                print(f"  {col:40s} = {row[col]}")


if __name__ == "__main__":
    main()