"""
Pure I/O loaders for the three heterogeneous raw sources described in
`data_dictionary.md`. No feature logic belongs here — only loading and basic
type coercion, so ingestion can be unit-tested and swapped independently of
`transforms.py`.
"""

from pathlib import Path

import pandas as pd


def load_customers(path: str = "data/customers.csv") -> pd.DataFrame:
    """Load customers.csv.

    Returns a DataFrame with columns: customer_id, signup_date, acquisition_channel,
    region, churned. signup_date is parsed as a datetime.
    """
    df = pd.read_csv(path)
    df["signup_date"] = pd.to_datetime(df["signup_date"])
    return df


def load_transactions(path: str = "data/transactions.db") -> pd.DataFrame:
    """Load the row-level `transactions` table from the SQLite database.

    Returns a DataFrame with columns: customer_id, txn_timestamp, category, channel,
    amount, is_returned. txn_timestamp is parsed as datetime; is_returned is cast to int.
    """
    import sqlite3

    conn = sqlite3.connect(path)
    df = pd.read_sql("SELECT * FROM transactions", conn)
    conn.close()

    df["txn_timestamp"] = pd.to_datetime(df["txn_timestamp"])
    df["is_returned"] = df["is_returned"].astype(int)
    return df


def load_monthly_agg(path: str = "data/transactions_monthly_agg.parquet") -> pd.DataFrame:
    """Load the pre-aggregated customer x month parquet extract.

    Returns a DataFrame with columns: customer_id, txn_month, txn_count, total_amount,
    return_count. txn_month is parsed as datetime.
    """
    df = pd.read_parquet(path)
    df["txn_month"] = pd.to_datetime(df["txn_month"])
    return df