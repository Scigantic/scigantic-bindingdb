"""Binding measurements, filtered the way that avoids BindingDB's two
sharpest edges: censored affinity values, and target joins that fan out on
multichain complexes.

Ki/IC50/Kd/EC50 are occasionally reported as ">X" or "<X" rather than an
exact value (an assay hit its ceiling or floor). exact_only=True, the
default, keeps only rows where that endpoint's qualifier is '=', so a
censored bound is never silently treated as a real affinity.

Filtering by target uses EXISTS against target_chains rather than a JOIN,
so a target whose UniProt ID appears on more than one chain of the same
complex still returns each measurement once, not once per matching chain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from .connection import connect
from .releases import latest

if TYPE_CHECKING:
    import pandas as pd

Endpoint = Literal["ki", "ic50", "kd", "ec50"]
_ENDPOINTS: tuple[Endpoint, ...] = ("ki", "ic50", "kd", "ec50")


def measurements(
    release: str | None = None,
    uniprot_id: str | None = None,
    endpoint: Endpoint = "ki",
    exact_only: bool = True,
    limit: int | None = None,
) -> "pd.DataFrame":
    """Binding measurements for one endpoint, most potent first.

    uniprot_id matches either UniProt (SwissProt or TrEMBL) primary ID on
    any chain of the target. A multichain complex needs the accession on
    only one chain to match, and matches once regardless of how many chains
    it appears on.

    exact_only (default True) keeps only rows where this endpoint's
    qualifier is '='. Set False to also see censored ">"/"<" bounds,
    which come back with their qualifier column intact rather than a bare
    number that looks exact but isn't.

    release defaults to the manifest's current latest().
    """
    if endpoint not in _ENDPOINTS:
        raise ValueError(f"endpoint must be one of {_ENDPOINTS}, got {endpoint!r}")
    release = release or latest()
    value_col, qual_col = f"{endpoint}_nm_value", f"{endpoint}_nm_qualifier"

    con = connect(release)
    try:
        where: list[str] = [f"{value_col} IS NOT NULL"]
        params: list[str | int] = []
        if exact_only:
            where.append(f"{qual_col} = '='")
        if uniprot_id is not None:
            where.append(
                "EXISTS (SELECT 1 FROM target_chains c WHERE "
                "c.reactant_set_id = measurements.reactant_set_id AND "
                "(c.uniprot_swissprot_primary_id = ? OR c.uniprot_trembl_primary_id = ?))"
            )
            params.extend([uniprot_id, uniprot_id])

        sql = (
            "SELECT * FROM measurements "
            f"WHERE {' AND '.join(where)} "
            f"ORDER BY {value_col} ASC"
        )
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        return con.execute(sql, params).df()
    finally:
        con.close()
