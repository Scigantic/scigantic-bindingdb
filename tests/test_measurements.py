import scigantic_bindingdb as bindingdb

# P00533 is EGFR's UniProt (SwissProt) accession. Counts verified against the
# live mirror on the 202608 release; update if a re-mirror changes them.
_EGFR = "P00533"


def test_egfr_exact_ki():
    df = bindingdb.measurements(uniprot_id=_EGFR, endpoint="ki")
    assert len(df) == 508
    assert (df["ki_nm_qualifier"] == "=").all()


def test_exact_only_false_includes_censored_rows():
    exact = bindingdb.measurements(uniprot_id=_EGFR, endpoint="ki", exact_only=True)
    everything = bindingdb.measurements(uniprot_id=_EGFR, endpoint="ki", exact_only=False)
    assert len(everything) == 579
    assert len(everything) > len(exact)
    assert set(everything["ki_nm_qualifier"]) >= {"=", ">"}


def test_sorted_most_potent_first():
    df = bindingdb.measurements(uniprot_id=_EGFR, endpoint="ki")
    assert df["ki_nm_value"].is_monotonic_increasing
    # The single most potent measured Ki for EGFR in this release.
    assert df["reactant_set_id"].iloc[0] == "50029862"
    assert df["ki_nm_value"].iloc[0] == 0.006


def test_uniprot_filter_matches_either_swissprot_or_trembl_chain():
    # No JOIN fan-out: each reactant_set_id appears at most once even though
    # the EXISTS check can match on more than one chain of a multichain
    # target.
    df = bindingdb.measurements(uniprot_id=_EGFR, endpoint="ki")
    assert df["reactant_set_id"].is_unique


def test_invalid_endpoint_raises():
    import pytest

    with pytest.raises(ValueError):
        bindingdb.measurements(endpoint="not_a_real_endpoint")  # type: ignore[arg-type]


def test_no_target_filter_returns_the_whole_corpus_for_the_endpoint():
    df = bindingdb.measurements(endpoint="kd", limit=10)
    assert len(df) == 10
    assert (df["kd_nm_qualifier"] == "=").all()
