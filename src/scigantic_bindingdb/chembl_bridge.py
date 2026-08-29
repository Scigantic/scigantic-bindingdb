"""Cross-reference BindingDB measurements to ChEMBL, through the precomputed
bridge table rather than re-deriving the join yourself.

BindingDB ingests ChEMBL as one of its own curated source feeds (51.3% of
measurements in the 202608 release), and ChEMBL separately absorbs some
BindingDB patent-derived bioactivity data, so the two archives are not
independent corpora. derived/bindingdb_chembl_bridge.parquet, built once at
mirror time, joins measurements to s3://scigantic-chembl by BindingDB's own
chembl_id column where present (authoritative) and falls back to an exact
InChIKey match where it's missing. This module wraps that file, and
optionally reaches into the live scigantic-chembl mirror over the same
DuckDB connection for compound/target names: a read-only cross-bucket SQL
join at query time, not a mount-level dependency between the two archives.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._constants import CHEMBL_BUCKET
from .cache import resolve as _resolve
from .connection import connect
from .releases import _require, latest

if TYPE_CHECKING:
    import pandas as pd


def chembl_bridge(
    release: str | None = None,
    chembl_release: str = "chembl_37",
    reactant_set_id: str | None = None,
    with_names: bool = True,
    limit: int | None = None,
) -> "pd.DataFrame":
    """BindingDB measurements joined to their ChEMBL cross-reference.

    with_names (default True) also pulls in compound_chembl_id's pref_name
    from s3://scigantic-chembl/<chembl_release>, a second public bucket read
    over the same connection. Set False to skip that join and get just the
    bridge table's own columns (reactant_set_id, chembl_molregno, chembl_id,
    match_method) plus the measurement's SMILES.

    release defaults to the manifest's current latest(). Only that release
    is guaranteed to carry the bridge table; call releases() to check.
    """
    release = release or latest()
    _require(release, "chembl_bridge")
    con = connect(release)
    try:
        bridge_path = _resolve(f"{release}/derived/bindingdb_chembl_bridge.parquet")

        where: list[str] = []
        params: list[str | int] = []
        if reactant_set_id is not None:
            where.append("b.reactant_set_id = ?")
            params.append(reactant_set_id)
        clause = f"WHERE {' AND '.join(where)}" if where else ""

        # read_parquet(bridge_path) inline rather than a named
        # CREATE VIEW: connect() now hands out a cursor on a base
        # connection shared across calls (see connection.py), and a
        # named view is catalog state on that shared connection.
        # Concurrent calls each doing CREATE OR REPLACE VIEW on the same
        # name raced each other's DDL transaction: reproduced directly,
        # concurrent chembl_bridge()/dti_pairs() calls from a thread pool
        # mostly failed with DuckDB's "Catalog write-write conflict".
        # Referencing the parquet file directly in the query has no
        # catalog side effect at all, so there's nothing to conflict on.
        if with_names:
            mol_dict = f"s3://{CHEMBL_BUCKET}/{chembl_release}/parquet/molecule_dictionary.parquet"
            sql = f"""
                SELECT b.reactant_set_id, b.chembl_molregno, b.chembl_id, b.match_method,
                       m.ligand_smiles, d.pref_name AS chembl_pref_name
                FROM read_parquet('{bridge_path}') b
                JOIN measurements m ON m.reactant_set_id = b.reactant_set_id
                LEFT JOIN read_parquet('{mol_dict}') d ON d.molregno = b.chembl_molregno
                {clause}
            """
        else:
            sql = f"""
                SELECT b.reactant_set_id, b.chembl_molregno, b.chembl_id, b.match_method,
                       m.ligand_smiles
                FROM read_parquet('{bridge_path}') b
                JOIN measurements m ON m.reactant_set_id = b.reactant_set_id
                {clause}
            """
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        return con.execute(sql, params).df()
    finally:
        con.close()
