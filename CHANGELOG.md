# Changelog

All notable changes to this project are documented here. Versions correspond to PyPI releases.

## 0.2.5 - 2026-08-31

- `query()` now stamps `df.attrs["bindingdb_release"]` with the release actually used, matching scigantic-chembl's own `query()`, which already does this for `chembl_release`.
- Added a "Data license" section to the README: BindingDB's underlying data is a per-row mix of CC BY 3.0 (BindingDB's own curated rows) and CC BY-SA 3.0 (rows imported from ChEMBL, keyed by the `curation_source` column), separate from and not superseded by this package's own MIT-0 code license. `chembl_bridge()` results specifically carry ChEMBL's share-alike terms on their ChEMBL-matched columns regardless of the underlying measurement's own source.
- Fixed repo discoverability: added GitHub topics and a homepage link (was previously unset).
- Added upper bounds to the `duckdb` and `pandas` dependency constraints, matching scigantic-chembl's bounds for the same libraries.
- Added `CHANGELOG.md`.
- Added `pytest-cov` as a local, non-CI-gating coverage option.

## 0.2.4 - 2026-08-29

- Coordinate concurrent first downloads of the same cache key: `resolve()`'s check-then-download is now guarded by a per-key lock, so concurrent callers asking for an uncached key wait for one download instead of each starting their own (#3).

## 0.2.3 - 2026-08-29

- Fixed a `chembl_bridge()`/`dti_pairs()` conflict under concurrent calls: both used a named `CREATE OR REPLACE VIEW` on the shared base connection, which raced on DuckDB's catalog under concurrent calls (#2).

## 0.2.2 - 2026-08-29

- `connect()` now reuses the DuckDB base connection across calls instead of rebuilding it every time.
- Fixed a cache download race: the temp filename used during download was deterministic (derived only from the cache key), so two threads racing to fill the same key could collide and raise `FileNotFoundError` on `os.replace()` (#1).

## 0.2.1 - 2026-08-28

- Validate `dti_pairs()`'s `endpoint` argument, matching `measurements()`'s existing validation.

## 0.2.0 - 2026-08-26

- Added `dti_pairs()`, a ready drug-target-interaction training table.

## 0.1.0 - 2026-08-26

- Initial release: query BindingDB from the public S3 mirror with DuckDB.
