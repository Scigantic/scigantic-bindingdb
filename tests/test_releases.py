import sys
import warnings

import pytest

import scigantic_bindingdb as bindingdb
from scigantic_bindingdb.releases import ReleaseCapabilityError, UnknownReleaseError


def test_releases_lists_known_releases():
    names = {r.release for r in bindingdb.releases()}
    assert "202608" in names


def test_latest_is_202608():
    assert bindingdb.latest() == "202608"


def test_202608_has_the_chembl_bridge():
    info = {r.release: r for r in bindingdb.releases()}["202608"]
    assert info.raw
    assert info.chembl_bridge
    assert info.dti_pairs


def test_unknown_release_raises():
    with pytest.raises(UnknownReleaseError):
        bindingdb.query("SELECT 1", release="999999")


def test_chembl_bridge_on_unknown_release_raises_capability_error():
    with pytest.raises((UnknownReleaseError, ReleaseCapabilityError)):
        bindingdb.chembl_bridge(release="999999")


def test_dti_pairs_on_unknown_release_raises_capability_error():
    with pytest.raises((UnknownReleaseError, ReleaseCapabilityError)):
        bindingdb.dti_pairs(release="999999")


def test_falls_back_when_manifest_unreachable():
    releases_module = sys.modules["scigantic_bindingdb.releases"]
    real_url, real_cache = releases_module._MANIFEST_URL, releases_module._cache
    releases_module._MANIFEST_URL = (
        "https://scigantic-bindingdb.s3.us-east-1.amazonaws.com/_DOES_NOT_EXIST.json"
    )
    releases_module._cache = None
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert bindingdb.latest() == "202608"
            assert {r.release for r in bindingdb.releases()} == {"202608"}
        assert len(caught) == 1
        assert issubclass(caught[0].category, UserWarning)
        assert "falling back" in str(caught[0].message)
    finally:
        releases_module._MANIFEST_URL, releases_module._cache = real_url, real_cache
