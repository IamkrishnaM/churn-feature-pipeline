"""
Local feature store API: a SQLite metadata/version registry (`feature_store/registry.db`,
table `feature_registry`) plus one parquet value snapshot per registered version
(`feature_store/values/<feature_name>__v<version>.parquet`).

Do not add mlflow, feast, or any other feature-store library — this store is SQLite +
parquet only.

Never hardcode a parquet filename outside this module — all reads must resolve the path
via the registry.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REGISTRY_DB = "feature_store/registry.db"
VALUES_DIR = "feature_store/values"


def _get_conn() -> sqlite3.Connection:
    """Get a connection to the registry DB, creating tables if they don't exist."""
    Path(REGISTRY_DB).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(REGISTRY_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feature_registry (
            feature_name    TEXT NOT NULL,
            version         INTEGER NOT NULL,
            created_at      TEXT NOT NULL,
            description     TEXT NOT NULL,
            source_columns  TEXT NOT NULL,
            transform_summary TEXT NOT NULL,
            business_rationale TEXT NOT NULL,
            parameters      TEXT NOT NULL,
            parquet_path    TEXT NOT NULL,
            is_latest       INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (feature_name, version)
        )
    """)
    return conn


def register_version(
    feature_name: str,
    values_df: pd.DataFrame,
    description: str,
    source_columns: str,
    transform_summary: str,
    business_rationale: str,
    parameters: dict,
) -> int:
    """Write a new parquet snapshot, insert the registry row, flip is_latest, return the
    new version number.

    Parameters
    ----------
    feature_name : str
        Logical name of the feature (e.g. 'txn_count_last_90d').
    values_df : pd.DataFrame
        Must contain columns: customer_id, the feature's own value column, and as_of_date.
    description : str
        One or two sentences, human-readable.
    source_columns : str
        Source file/table + column(s), e.g. 'data/transactions.db:transactions.amount'.
    transform_summary : str
        Short prose description of the computation.
    business_rationale : str
        Why this feature exists / why this version differs from the prior one.
    parameters : dict
        Tunable parameter values for this version (e.g. {"window_days": 90}).
        Empty dict if none.

    Returns
    -------
    int
        The new version number.
    """
    Path(VALUES_DIR).mkdir(parents=True, exist_ok=True)
    conn = _get_conn()

    try:
        # Determine the next version number
        cursor = conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM feature_registry WHERE feature_name = ?",
            (feature_name,),
        )
        new_version = cursor.fetchone()[0]

        # Build parquet path
        parquet_path = f"{VALUES_DIR}/{feature_name}__v{new_version}.parquet"

        # Write the parquet snapshot
        values_df.to_parquet(parquet_path, index=False)

        # Insert the registry row and flip is_latest in one transaction
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("BEGIN")
        conn.execute(
            """
            UPDATE feature_registry SET is_latest = 0
            WHERE feature_name = ? AND is_latest = 1
            """,
            (feature_name,),
        )
        conn.execute(
            """
            INSERT INTO feature_registry
                (feature_name, version, created_at, description, source_columns,
                 transform_summary, business_rationale, parameters, parquet_path, is_latest)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                feature_name,
                new_version,
                now,
                description,
                source_columns,
                transform_summary,
                business_rationale,
                json.dumps(parameters),
                parquet_path,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return new_version


def get_latest(feature_name: str) -> pd.DataFrame:
    """Return the DataFrame for the version currently flagged is_latest = 1."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT parquet_path FROM feature_registry WHERE feature_name = ? AND is_latest = 1",
        (feature_name,),
    ).fetchone()
    conn.close()

    if row is None:
        raise ValueError(
            f"No registered version found for feature '{feature_name}'"
        )
    return pd.read_parquet(row[0])


def get_version(feature_name: str, version: int) -> pd.DataFrame:
    """Return the DataFrame for a specific (feature_name, version)."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT parquet_path FROM feature_registry WHERE feature_name = ? AND version = ?",
        (feature_name, version),
    ).fetchone()
    conn.close()

    if row is None:
        raise ValueError(
            f"Version {version} not found for feature '{feature_name}'"
        )
    return pd.read_parquet(row[0])


def list_versions(feature_name: str) -> pd.DataFrame:
    """Return every registered version's metadata row for feature_name, most recent first."""
    conn = _get_conn()
    df = pd.read_sql(
        "SELECT * FROM feature_registry WHERE feature_name = ? ORDER BY version DESC",
        conn,
        params=(feature_name,),
    )
    conn.close()
    return df