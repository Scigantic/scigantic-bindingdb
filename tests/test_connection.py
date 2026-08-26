"""Real queries against the live public mirror, no mocks.

Network-dependent by design: the whole point of this package is that it
answers real queries against real data with no local setup, so that is what
gets tested.
"""

import scigantic_bindingdb as bindingdb


def test_query_returns_dataframe_with_expected_columns():
    df = bindingdb.query(
        "SELECT reactant_set_id, ligand_smiles FROM measurements LIMIT 5"
    )
    assert list(df.columns) == ["reactant_set_id", "ligand_smiles"]
    assert len(df) == 5


def test_connect_registers_all_five_core_tables():
    con = bindingdb.connect()
    try:
        for table in ("measurements", "target_chains", "target_chain_names", "assays", "id_mappings"):
            n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            assert n > 0, table
    finally:
        con.close()


def test_measurements_row_count():
    # Exact count verified against the live mirror on the 202608 release;
    # update this if a future re-mirror changes it.
    df = bindingdb.query("SELECT count(*) AS n FROM measurements")
    assert df["n"].iloc[0] == 3234499
