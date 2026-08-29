"""Real queries against the live public mirror, no mocks.

Network-dependent by design: the whole point of this package is that it
answers real queries against real data with no local setup, so that is what
gets tested.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

import scigantic_bindingdb as bindingdb
import scigantic_bindingdb.connection as _connection_module


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


def test_base_connection_is_reused_not_rebuilt_per_call():
    _connection_module._base_cons.clear()  # force a fresh base connection
    bindingdb.connect().close()
    first = _connection_module._base_cons[bindingdb.latest()]
    assert first is not None
    bindingdb.connect().close()
    # Same base connection object, not rebuilt: this is what makes repeat
    # calls to measurements()/chembl_bridge()/dti_pairs()/query() skip
    # re-running INSTALL/LOAD httpfs, re-creating the S3 secret, and
    # re-registering all five views every time.
    assert _connection_module._base_cons[bindingdb.latest()] is first


def test_concurrent_connect_from_multiple_threads_creates_one_base_connection():
    _connection_module._base_cons.clear()  # force the lazy-init race on every thread

    def touch(_i):
        con = bindingdb.connect()
        try:
            return con.execute("SELECT 1").fetchone()[0]
        finally:
            con.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(touch, range(8)))

    assert results == [1] * 8
    assert len(_connection_module._base_cons) == 1  # exactly one base connection exists now


def test_concurrent_cursors_return_correct_distinct_results():
    # Guards against a real bug, not a hypothetical one: a single shared
    # DuckDB Connection is not safe for concurrent execute()/fetchone()
    # calls from multiple threads. connect() hands out a fresh cursor()
    # per call specifically to avoid this; this proves two different
    # queries running concurrently on cursors of the same base connection
    # each get their own correct result rather than a corrupted or
    # cross-contaminated one.
    uniprot_ids = ["P00533", "P35462"]  # EGFR, DRD3
    sequential = {
        uid: bindingdb.query(
            "SELECT count(*) AS n FROM measurements m WHERE EXISTS ("
            "SELECT 1 FROM target_chains c WHERE c.reactant_set_id = m.reactant_set_id "
            f"AND c.uniprot_swissprot_primary_id = '{uid}')"
        )["n"].iloc[0]
        for uid in uniprot_ids
    }

    results = {}
    lock = threading.Lock()

    def worker(uid):
        n = bindingdb.query(
            "SELECT count(*) AS n FROM measurements m WHERE EXISTS ("
            "SELECT 1 FROM target_chains c WHERE c.reactant_set_id = m.reactant_set_id "
            f"AND c.uniprot_swissprot_primary_id = '{uid}')"
        )["n"].iloc[0]
        with lock:
            results[uid] = n

    threads = [threading.Thread(target=worker, args=(uid,)) for uid in uniprot_ids * 4]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for uid in uniprot_ids:
        assert results[uid] == sequential[uid]
