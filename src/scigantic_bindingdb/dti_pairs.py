"""(Ligand, target, affinity) triples, ready for a drug-target-interaction
or proteochemometric model to train on.

BindingDB is the dataset most DTI tooling (DeepPurpose and similar) is built
around, specifically because it ships a full protein sequence alongside
every affinity measurement -- something ChEMBL's bioactivity tables don't
do as directly. This wraps derived/dti_pairs.parquet, the pre-filtered,
pre-transformed version of that pairing: exact measurements only (a
censored ">"/"<" bound is never a usable regression label), chain 1's
sequence required, and p_affinity already computed as -log10(affinity_nm *
1e-9), the same transform as ChEMBL's pchembl_value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from .cache import resolve as _resolve
from .connection import connect
from .releases import _require, latest

if TYPE_CHECKING:
    import pandas as pd

Endpoint = Literal["ki", "ic50", "kd", "ec50"]


def dti_pairs(
    release: str | None = None,
    endpoint: Endpoint | None = None,
    uniprot_id: str | None = None,
    single_chain_only: bool = False,
    limit: int | None = None,
) -> "pd.DataFrame":
    """Ligand/target/affinity triples for DTI or proteochemometric training.

    endpoint filters to one of 'ki', 'ic50', 'kd', 'ec50'; omit to get all
    four (a row's `endpoint` column says which).

    single_chain_only=True drops rows whose target came from a complex with
    more than one declared chain (n_chains_declared > 1) -- those rows still
    represent the interaction with chain 1's sequence only, which is fine
    for most uses, but exclude them if single-chain purity matters for your
    model.

    release defaults to the manifest's current latest(). Only that release
    is guaranteed to carry this file; call releases() to check.
    """
    release = release or latest()
    _require(release, "dti_pairs")
    con = connect(release)
    try:
        path = _resolve(f"{release}/derived/dti_pairs.parquet")
        con.execute(f"CREATE OR REPLACE VIEW dti_pairs AS SELECT * FROM read_parquet('{path}')")

        where: list[str] = []
        params: list[str | int] = []
        if endpoint is not None:
            where.append("endpoint = ?")
            params.append(endpoint)
        if uniprot_id is not None:
            where.append("uniprot_id = ?")
            params.append(uniprot_id)
        if single_chain_only:
            where.append("n_chains_declared = 1")
        clause = f"WHERE {' AND '.join(where)}" if where else ""

        sql = f"SELECT * FROM dti_pairs {clause} ORDER BY p_affinity DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        return con.execute(sql, params).df()
    finally:
        con.close()
