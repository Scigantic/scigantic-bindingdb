"""DuckDB connection helpers. Queries run against the public S3 mirror over
httpfs, no download.

This module deliberately does not participate in enable_cache() (see
cache.py): connect() registers all five core tables as views, the largest
over 200 MB, so caching them here would mean any call to connect() or
query() eagerly downloads everything regardless of what the query actually
touches. Caching applies to chembl_bridge() instead, which needs exactly
one known file.

connect() used to open a brand new duckdb.connect() on every single call,
including from measurements(), chembl_bridge(), dti_pairs() and query(),
each of which calls it once per invocation and closes it when done. That
re-ran INSTALL/LOAD httpfs, re-created the S3 secret, and re-registered all
five views from scratch every time, on top of discarding whatever DuckDB
itself caches about a remote parquet file (footer, row group metadata)
along with the connection. Looping any of those functions, the way a
notebook computing measurements() per target or dti_pairs() per endpoint
does, re-paid that setup cost on every call. connect() now hands out a
cursor() on a lazily-created, shared base connection per release instead:
the base connection's setup happens once per (release, process), and every
caller still gets an independent handle safe to use, and close(), on its
own.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from ._constants import BUCKET, REGION
from .releases import _validate_release, latest

if TYPE_CHECKING:
    import duckdb
    import pandas as pd

# Registered as views on the base connection so plain SQL can reference a
# table by name instead of a full read_parquet() path.
_CORE_TABLES = (
    "measurements",
    "target_chains",
    "target_chain_names",
    "assays",
    "id_mappings",
)

# One base connection per release, built the first time that release is
# used and reused after that. Keyed by release rather than a single shared
# connection because the five views above are release-specific SQL text;
# a process that queries more than one release still only pays setup once
# per release, not once per call.
_base_cons: dict[str, "duckdb.DuckDBPyConnection"] = {}
_base_cons_lock = threading.Lock()


def _get_base_connection(release: str) -> "duckdb.DuckDBPyConnection":
    con = _base_cons.get(release)
    if con is not None:
        return con
    with _base_cons_lock:
        con = _base_cons.get(release)
        if con is None:  # re-check: another thread may have won the race
            import duckdb

            new_con = duckdb.connect()
            # DuckDB auto-shows an ASCII progress bar for queries it
            # estimates will take a while, on stdout, regardless of
            # whether that's a real terminal. Surprising output for a
            # library call in a notebook or script, so it's off here by
            # default.
            new_con.execute("SET enable_progress_bar=false")
            new_con.execute("INSTALL httpfs")
            new_con.execute("LOAD httpfs")
            new_con.execute(f"SET s3_region='{REGION}'")
            # The mirror is public-read. Without this, DuckDB looks for
            # AWS credentials and fails on a machine that has none
            # configured.
            new_con.execute(
                "CREATE OR REPLACE SECRET scigantic_bindingdb "
                "(TYPE s3, PROVIDER config, KEY_ID '', SECRET '')"
            )

            base = f"s3://{BUCKET}/{release}/parquet"
            for table in _CORE_TABLES:
                new_con.execute(
                    f"CREATE OR REPLACE VIEW {table} AS "
                    f"SELECT * FROM read_parquet('{base}/{table}.parquet')"
                )
            _base_cons[release] = new_con
            con = new_con
    return con


def connect(release: str | None = None) -> "duckdb.DuckDBPyConnection":
    """A DuckDB connection against s3://scigantic-bindingdb.

    `SELECT * FROM measurements` works directly; any other table under
    `<release>/parquet/` is reachable with
    `read_parquet('s3://scigantic-bindingdb/<release>/parquet/<table>.parquet')`.

    release defaults to whatever the live manifest currently calls latest(),
    resolved at call time rather than import time.

    Returns an independent cursor() on a shared base connection for this
    release rather than a brand new duckdb.connect() each time: a single
    DuckDB Connection is not safe for concurrent execute() calls from
    multiple threads (verified directly: two threads racing
    execute()/fetchone() on the same connection can silently return the
    wrong row instead of raising), so callers get their own cursor rather
    than sharing one connection object directly. close() closes only that
    cursor; the base connection and its registered views stay alive for
    the next call to reuse.
    """
    release = release or latest()
    _validate_release(release)
    return _get_base_connection(release).cursor()


def query(sql: str, release: str | None = None) -> "pd.DataFrame":
    """Run SQL against a release and return a pandas DataFrame.

    For several queries against the same release, call connect() once and
    reuse it instead, to avoid opening and closing a cursor per query.
    """
    con = connect(release)
    try:
        return con.execute(sql).df()
    finally:
        con.close()
