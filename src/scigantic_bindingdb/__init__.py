"""Query BindingDB directly from a public S3 mirror. No download, no local database."""

from importlib.metadata import PackageNotFoundError, version as _version

from .cache import cache_dir, disable_cache, enable_cache, is_cache_enabled
from .cache import resolve as cache_resolve
from .chembl_bridge import chembl_bridge
from .connection import connect, query
from .dti_pairs import dti_pairs
from .measurements import measurements
from .releases import (
    ReleaseCapabilityError,
    ReleaseInfo,
    UnknownReleaseError,
    latest,
    releases,
)

try:
    __version__ = _version("scigantic-bindingdb")
except PackageNotFoundError:
    # Running from a source checkout with no install (editable or not).
    __version__ = "0.0.0"

__all__ = [
    "chembl_bridge",
    "connect",
    "query",
    "measurements",
    "dti_pairs",
    "releases",
    "latest",
    "enable_cache",
    "disable_cache",
    "is_cache_enabled",
    "cache_dir",
    "cache_resolve",
    "ReleaseInfo",
    "ReleaseCapabilityError",
    "UnknownReleaseError",
]
