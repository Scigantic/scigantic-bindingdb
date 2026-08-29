"""Optional local caching: download once, then work with no network.

Off by default. This package's whole pitch is zero setup, so caching stays
opt-in rather than something that changes the default behavior:

    import scigantic_bindingdb as bindingdb
    bindingdb.enable_cache()

chembl_bridge() then reads its one derived file from a local cache directory
instead of S3, downloading it the first time it's needed and reusing it
after that.

connect() / query() / measurements() deliberately do NOT use this:
connect() registers five core tables as views on every call, so caching
them there would mean any call eagerly downloads everything regardless of
what the query actually touches. Cache a specific table yourself if you
want it locally: cache_resolve("<release>/parquet/<table>.parquet")
downloads it and returns the local path, usable directly in
read_parquet(...).
"""

from __future__ import annotations

import os
import sys
import threading
import urllib.request
import uuid
from pathlib import Path

from ._constants import BUCKET, REGION

_enabled = False
_cache_dir: Path | None = None

_CHUNK_BYTES = 1024 * 1024

# One lock per key, created on first use. Guards resolve()'s
# check-then-download against concurrent callers asking for the same key
# at once: without this, N threads racing the first resolve() of a key
# each see it missing and each download it in full, rather than one
# downloading while the rest wait and reuse the result. Verified directly:
# 16 threads calling chembl_bridge() concurrently on an empty cache
# triggered 16 separate downloads of the same file before this fix.
_resolve_locks: dict[str, threading.Lock] = {}
_resolve_locks_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    lock = _resolve_locks.get(key)
    if lock is not None:
        return lock
    with _resolve_locks_guard:
        return _resolve_locks.setdefault(key, threading.Lock())


def _default_cache_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Caches")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "scigantic-bindingdb"


def enable_cache(cache_dir: str | None = None) -> Path:
    """Turn on local caching for every function in this package that uses it.

    Cache location: `cache_dir` if given, else the
    SCIGANTIC_BINDINGDB_CACHE environment variable, else a
    platform-appropriate user cache directory. Returns the resolved
    directory.
    """
    global _enabled, _cache_dir
    if cache_dir is not None:
        resolved = Path(cache_dir)
    elif os.environ.get("SCIGANTIC_BINDINGDB_CACHE"):
        resolved = Path(os.environ["SCIGANTIC_BINDINGDB_CACHE"])
    else:
        resolved = _default_cache_dir()
    resolved.mkdir(parents=True, exist_ok=True)
    _cache_dir = resolved
    _enabled = True
    return resolved


def disable_cache() -> None:
    """Turn caching back off. Later calls go straight to S3 again.

    Anything already downloaded stays on disk; this only stops using it.
    """
    global _enabled
    _enabled = False


def is_cache_enabled() -> bool:
    return _enabled


def cache_dir() -> Path | None:
    """The resolved cache directory, or None if caching has never been enabled."""
    return _cache_dir


def _atomic_download(url: str, local_path: Path) -> None:
    """Stream `url` to a sibling temp file, then rename it into place.

    The rename is atomic, so a download killed partway through never leaves
    something at `local_path` that looks cached but isn't: readers only
    ever see the old state (temp file, ignored) or the new one (fully
    written, renamed), never a partial write.

    The temp filename is unique per call, not just per `local_path`: two
    threads racing to fill the same key (e.g. two callers both hitting
    chembl_bridge() for the first time at once) must not share a temp
    path, or the second os.replace() below raises FileNotFoundError once
    the first has already consumed it. Verified directly with a 16-thread
    stress run against one shared local_path before this fix reliably
    raised that; last writer's os.replace() wins now, which is fine since
    every writer here is downloading the same immutable S3 key.
    """
    tmp_path = local_path.with_name(local_path.name + f".{uuid.uuid4().hex}.part")
    with urllib.request.urlopen(url) as response, open(tmp_path, "wb") as fh:
        while chunk := response.read(_CHUNK_BYTES):
            fh.write(chunk)
    os.replace(tmp_path, local_path)


def resolve(key: str) -> str:
    """An S3 URL, or a local cached file path if caching is on.

    `key` is a path relative to the bucket root, e.g.
    "202608/derived/bindingdb_chembl_bridge.parquet". Downloads to the
    cache on first access; later calls for the same key reuse the local
    file without touching the network. Concurrent callers asking for the
    same key while it's still downloading wait for that download rather
    than each starting their own.
    """
    if not _enabled:
        return f"s3://{BUCKET}/{key}"

    assert _cache_dir is not None
    local_path = _cache_dir / key
    if local_path.exists():
        return str(local_path)

    with _lock_for(key):
        if local_path.exists():  # another thread finished it while we waited
            return str(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://{BUCKET}.s3.{REGION}.amazonaws.com/{key}"
        print(f"scigantic-bindingdb: caching {key} ...", file=sys.stderr, flush=True)
        _atomic_download(url, local_path)
    return str(local_path)
