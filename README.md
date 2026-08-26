<h1 align="center">scigantic-bindingdb</h1>

<p align="center">
    <a href="https://github.com/Scigantic/scigantic-bindingdb/actions/workflows/ci.yml">
        <img alt="CI" src="https://github.com/Scigantic/scigantic-bindingdb/actions/workflows/ci.yml/badge.svg" /></a>
    <a href="https://pypi.org/project/scigantic-bindingdb/">
        <img alt="PyPI" src="https://img.shields.io/pypi/v/scigantic-bindingdb" /></a>
    <a href="https://pypi.org/project/scigantic-bindingdb/">
        <img alt="PyPI - Python Version" src="https://img.shields.io/pypi/pyversions/scigantic-bindingdb" /></a>
    <a href="https://github.com/Scigantic/scigantic-bindingdb/blob/main/LICENSE">
        <img alt="License" src="https://img.shields.io/github/license/Scigantic/scigantic-bindingdb" /></a>
</p>

Query BindingDB directly from a public S3 mirror with DuckDB.

```python
import scigantic_bindingdb as bindingdb

df = bindingdb.query("""
    SELECT reactant_set_id, ligand_smiles, ki_nm_value
    FROM measurements
    WHERE ki_nm_value IS NOT NULL
    LIMIT 5
""")
```

That query runs against `s3://scigantic-bindingdb` over DuckDB's httpfs extension. Nothing is downloaded first, and there's no local database file sitting on disk afterward.

## Installation

```console
$ pip install scigantic-bindingdb
```

## What's different about BindingDB

Every row is one binding measurement (Ki, IC50, Kd or EC50) between one ligand and one protein target, rather than ChEMBL's assay-centric bioactivity record. BindingDB ships no relational database, just a flat TSV; the mirror normalizes it into `measurements` (one row per measurement), `target_chains` (one row per protein chain of the target -- BindingDB's raw format repeats a column block once per chain in a multimer) and `target_chain_names`.

## Measurements, filtered the way that avoids the two sharp edges

```python
df = bindingdb.measurements(uniprot_id="P00533", endpoint="ki")  # EGFR
```

Two things this does that a raw query on `measurements` doesn't do for you:

**Censored values stay out unless you ask for them.** Ki/IC50/Kd/EC50 are occasionally reported as `>X` or `<X` rather than an exact value, the same idea as ChEMBL's `standard_relation`. `exact_only=True`, the default, keeps only rows where that endpoint's qualifier is `=`:

```python
df = bindingdb.measurements(uniprot_id="P00533", endpoint="ic50", exact_only=False)  # include censored bounds too
```

**Target filtering doesn't fan out on multichain complexes.** `uniprot_id` matches against `target_chains` with an `EXISTS` check, not a `JOIN`, so a target whose accession appears on more than one chain of the same complex still returns each measurement once.

`bindingdb.query()` still reaches the raw tables directly for anything this leaves out.

## Cross-referencing ChEMBL

BindingDB ingests ChEMBL as one of its own curated source feeds (51.3% of measurements in the 202608 release), and ChEMBL separately absorbs some BindingDB patent-derived bioactivity data -- the two archives are not independent corpora. `derived/bindingdb_chembl_bridge.parquet`, built once at mirror time, joins measurements to [scigantic-chembl](https://github.com/Scigantic/scigantic-chembl) by BindingDB's own `chembl_id` column where present (authoritative) and falls back to an exact InChIKey match where it's missing:

```python
df = bindingdb.chembl_bridge(reactant_set_id="50000001")
```

`with_names=True` (the default) also reaches into the live `scigantic-chembl` mirror for the matched compound's ChEMBL preferred name, a second public-bucket read over the same connection -- not a mount-level dependency between the two archives, just a query-time join across two buckets that are both public and read-only here.

## Working offline

Off by default, since zero setup is the whole point. Turn it on to run the same queries repeatedly without re-fetching from S3:

```python
import scigantic_bindingdb as bindingdb

bindingdb.enable_cache()
df = bindingdb.chembl_bridge()  # downloads the bridge table once, then reads from disk
```

`chembl_bridge()` needs exactly one derived file, so caching downloads that one file to `~/.cache/scigantic-bindingdb` (override with `enable_cache(cache_dir=...)` or the `SCIGANTIC_BINDINGDB_CACHE` environment variable) and reuses it after that.

`connect()`, `query()` and `measurements()` don't participate in this: `connect()` registers five core tables as views on every call, so caching them there would mean any call eagerly downloads everything regardless of what the query actually touches. Cache one table yourself if you want it locally: `bindingdb.cache_resolve("202608/parquet/measurements.parquet")` downloads it and returns the local path, usable directly in `read_parquet(...)`.

## What's mirrored

```python
bindingdb.releases()
```

| release | raw tables | ChEMBL bridge |
|---|---|---|
| 202608 | yes | yes |

This table isn't hardcoded. `releases()` reads a small manifest published alongside each mirror run. If it can't be reached, calls fall back to the snapshot shipped with whatever version you have installed and print a warning, rather than failing outright.

Not mirrored yet: BindingDB's 3D SDF structures and precomputed similarity/substructure search (no fingerprint corpus has been built for this archive) -- `bindingdb.query()` still reaches every raw table the mirror carries.

## Command line

```console
$ scigantic-bindingdb info
$ scigantic-bindingdb query "SELECT count(*) FROM measurements" --release 202608
```

## License

MIT-0. See [LICENSE](LICENSE).
