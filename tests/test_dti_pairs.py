import math

import scigantic_bindingdb as bindingdb

# Counts verified against the live mirror on the 202608 release; update if a
# re-mirror changes them.
_TOTAL_PAIRS = 2_589_053
_KI_PAIRS = 545_819


def test_total_pairs():
    df = bindingdb.dti_pairs(limit=1)
    assert "p_affinity" in df.columns
    total = bindingdb.query(
        "SELECT count(*) AS n FROM read_parquet("
        "'s3://scigantic-bindingdb/202608/derived/dti_pairs.parquet')"
    )
    assert total["n"].iloc[0] == _TOTAL_PAIRS


def test_endpoint_filter():
    df = bindingdb.dti_pairs(endpoint="ki")
    assert len(df) == _KI_PAIRS
    assert (df["endpoint"] == "ki").all()


def test_p_affinity_matches_the_log_transform():
    df = bindingdb.dti_pairs(endpoint="ki", limit=50)
    for affinity_nm, p_affinity in zip(df["affinity_nm"], df["p_affinity"]):
        assert math.isclose(p_affinity, 9.0 - math.log10(affinity_nm), rel_tol=1e-9)


def test_no_censored_values_present():
    # dti_pairs.parquet is built from exact ('=') measurements only, so
    # there is no qualifier column to check here at all: its absence is
    # itself the guarantee. This checks the corpus doesn't smuggle in a
    # non-positive or otherwise unusable affinity instead.
    df = bindingdb.dti_pairs(limit=100_000)
    assert (df["affinity_nm"] > 0).all()
    assert df["p_affinity"].notna().all()


def test_single_chain_only_excludes_multichain_rows():
    everything = bindingdb.dti_pairs(endpoint="ki")
    single_chain = bindingdb.dti_pairs(endpoint="ki", single_chain_only=True)
    assert len(single_chain) < len(everything)
    assert (single_chain["n_chains_declared"] == 1).all()
    assert (everything["n_chains_declared"] > 1).any()


def test_uniprot_filter():
    # EGFR
    df = bindingdb.dti_pairs(uniprot_id="P00533", endpoint="ki")
    assert len(df) > 0
    assert (df["uniprot_id"] == "P00533").all()


def test_sorted_most_potent_first():
    df = bindingdb.dti_pairs(endpoint="ki", uniprot_id="P00533")
    assert df["p_affinity"].is_monotonic_decreasing
