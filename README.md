# DataMingler Python

This folder is the cleaned Python version of the legacy `DataMingler-main` implementation.

The legacy project mixed PHP, Java, Redis, Neo4j, vendored JARs, generated files, datasets, presentations, and temporary outputs in one directory. This version keeps the same core architecture but makes it modular:

- `DVMGraph`: attributes and `has` edges.
- `DataSourceRegistry`: XML datasource definitions.
- `QueryPlan`: QDVM text/XML query representation.
- `KeyListStore`: in-memory replacement for the legacy Redis key-list structures.
- `QueryEvaluator`: materializes DVM edges, applies transformations, evaluates theta selections, and exports JSON/CSV.

## Quick Start

Run tests:

```powershell
cd C:\Users\anast\datamingler\datamingler
$env:PYTHONPATH = "."
python -m unittest discover -s tests
```

Evaluate the included example:

```powershell
cd C:\Users\anast\datamingler\datamingler
$env:PYTHONPATH = "."
python -m datamingler.cli eval examples\sample.dvm.xml examples\datasources.xml examples\customer_summary.qdvm --format json
```

Parse a legacy text query to XML:

```powershell
python -m datamingler.cli parse-query examples\customer_summary.qdvm --output examples\customer_summary.qdvm.xml
```

## Supported Legacy Features

- DVM XML load/save using the legacy `<edges>` format.
- Datasource XML load/save using the legacy `<datasources>` format.
- QDVM query text and query XML.
- CSV sources.
- Excel sources when `openpyxl` is installed.
- SQLite DB sources using the standard library.
- SQLAlchemy DB sources when `sqlalchemy` is installed and the datasource connection is a SQLAlchemy URL.
- Process sources that stream delimited stdout.
- Transformations:
  - `aggregate:min|max|sum|average|avg|count|any`
  - `filter:<python expression using $Label$>`
  - `map:python,<optional module>,<python expression using $Label$>`
- `where` theta expressions using `$RootLabel$` and child placeholders such as `$Age$`.

## What Was Removed

The new implementation intentionally does not copy generated `.class` files, JARs, ZIP/RAR archives, `node_modules`, Composer vendor folders, PPTs, temp JSON/CSV outputs, backup files, and old UI experiments. Those remain in `DataMingler-main` only as historical reference.

## Optional Integrations

Neo4j is no longer required to evaluate a query. The compatibility adapter can still load/save the legacy graph schema:

```powershell
python -m datamingler.cli load-neo4j examples\sample.dvm.xml --reset
python -m datamingler.cli save-neo4j --output exported.dvm.xml
```

Redis is no longer required. `KeyListStore` preserves the old Redis data layout semantics in memory, which makes tests and local execution deterministic.
