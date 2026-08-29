from concurrent.futures import ThreadPoolExecutor

import scigantic_bindingdb as bindingdb

# A gefitinib measurement, verified against the live mirror to resolve
# through the bridge table to CHEMBL939 / "GEFITINIB" in scigantic-chembl.
_GEFITINIB_REACTANT_SET_ID = "50891275"


def test_bridge_resolves_a_known_measurement_to_chembl():
    df = bindingdb.chembl_bridge(reactant_set_id=_GEFITINIB_REACTANT_SET_ID, with_names=False)
    assert len(df) == 1
    assert df["chembl_id"].iloc[0] == "CHEMBL939"
    assert df["match_method"].iloc[0] == "chembl_id_column"


def test_with_names_pulls_the_chembl_preferred_name():
    df = bindingdb.chembl_bridge(reactant_set_id=_GEFITINIB_REACTANT_SET_ID, with_names=True)
    assert df["chembl_pref_name"].iloc[0] == "GEFITINIB"


def test_bridge_total_row_count():
    # 70.2% of the 202608 release's 3,234,499 measurements resolve to a
    # ChEMBL molregno through this table. Update if a re-mirror or a new
    # ChEMBL release this bridges against changes the match rate.
    df = bindingdb.chembl_bridge(with_names=False, limit=1)
    assert "chembl_molregno" in df.columns

    total = bindingdb.query(
        "SELECT count(*) AS n FROM read_parquet("
        "'s3://scigantic-bindingdb/202608/derived/bindingdb_chembl_bridge.parquet')"
    )
    assert total["n"].iloc[0] == 2272063


def test_concurrent_calls_do_not_conflict_on_catalog():
    # Regression test for a real bug introduced by connect()'s move to a
    # shared base connection (see connection.py): chembl_bridge() used to
    # register its result as a named CREATE OR REPLACE VIEW, which is
    # catalog-mutating DDL. Two calls racing that DDL on the same shared
    # connection from different threads mostly failed with DuckDB's
    # "Catalog write-write conflict", reproduced directly (46/48 calls
    # failed in a 24-thread stress run) before this was fixed by
    # referencing the parquet file inline instead of via a named view.
    def call(i):
        return bindingdb.chembl_bridge(
            reactant_set_id=_GEFITINIB_REACTANT_SET_ID, with_names=(i % 2 == 0)
        )

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(call, range(16)))

    for df in results:
        assert len(df) == 1
        assert df["chembl_id"].iloc[0] == "CHEMBL939"
