"""DuckDB connection helpers. Queries run against the public S3 mirror over
httpfs, no download.

This module deliberately does not participate in enable_cache() (see
cache.py): connect() registers all five core tables as views on every call,
the largest over 200 MB, so caching them here would mean any call to
connect() or query() eagerly downloads everything regardless of what the
query actually touches. Caching applies to chembl_bridge() instead, which
needs exactly one known file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._constants import BUCKET, REGION
from .releases import _validate_release, latest

if TYPE_CHECKING:
    import duckdb
    import pandas as pd

# Registered as views on connect() so plain SQL can reference a table by
# name instead of a full read_parquet() path.
_CORE_TABLES = (
    "measurements",
    "target_chains",
    "target_chain_names",
    "assays",
    "id_mappings",
)


def connect(release: str | None = None) -> "duckdb.DuckDBPyConnection":
    """Open a DuckDB connection against s3://scigantic-bindingdb.

    `SELECT * FROM measurements` works directly; any other table under
    `<release>/parquet/` is reachable with
    `read_parquet('s3://scigantic-bindingdb/<release>/parquet/<table>.parquet')`.

    release defaults to whatever the live manifest currently calls latest(),
    resolved at call time rather than import time.
    """
    import duckdb

    release = release or latest()
    _validate_release(release)

    con = duckdb.connect()
    # DuckDB auto-shows an ASCII progress bar for queries it estimates will
    # take a while, on stdout, regardless of whether that's a real terminal.
    # Surprising output for a library call in a notebook or script, so it's
    # off here by default.
    con.execute("SET enable_progress_bar=false")
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    con.execute(f"SET s3_region='{REGION}'")
    # The mirror is public-read. Without this, DuckDB looks for AWS
    # credentials and fails on a machine that has none configured.
    con.execute(
        "CREATE OR REPLACE SECRET scigantic_bindingdb "
        "(TYPE s3, PROVIDER config, KEY_ID '', SECRET '')"
    )

    base = f"s3://{BUCKET}/{release}/parquet"
    for table in _CORE_TABLES:
        con.execute(
            f"CREATE OR REPLACE VIEW {table} AS "
            f"SELECT * FROM read_parquet('{base}/{table}.parquet')"
        )
    return con


def query(sql: str, release: str | None = None) -> "pd.DataFrame":
    """Run SQL against a release and return a pandas DataFrame.

    Opens a new connection per call. For several queries against the same
    release, call connect() once and reuse it instead.
    """
    con = connect(release)
    try:
        return con.execute(sql).df()
    finally:
        con.close()
