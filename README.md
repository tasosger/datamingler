# DataMingler Python

Clean Python rewrite of the legacy Java/PHP DataMingler stack.
Same core architecture (DVM graph, Redis key-list store, QDVM query language),
no Java, no PHP, no Neo4j dependency.

---

## Running with Docker (recommended)

The only prerequisite is **Docker Desktop** — it handles Redis, Neo4j, the Python backend, and the Next.js frontend automatically.

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. Start everything:

```powershell
docker compose up --build
```

The first run takes a few minutes while Docker downloads images and builds the containers. Once it's ready, open **http://localhost:3000**.

On subsequent starts you can skip `--build`:

```powershell
docker compose up
```

The UI has three tabs:

| Tab | What you can do |
|-----|----------------|
| **DVM Canvas** | View the DVM graph; click an edge to inspect it and toggle its *selected* flag; add or delete edges |
| **Query Builder** | Write QDVM queries and run them; results shown as JSON or CSV |
| **Datasources** | List, add, and delete datasources |

---

## Running manually (without Docker)

### Prerequisites

| Tool | Minimum version | Notes |
|------|----------------|-------|
| Python | 3.10 | `python --version` |
| Node.js | 18 | for the Next.js frontend — `node --version` |
| Redis | 6.x | Required to run queries; not needed just to run tests |
| Neo4j | 5.x | Stores the DVM graph; required to run the server |

Optional Python extras:

| Extra | Package installed | Needed for |
|-------|------------------|-----------|
| `excel` | `openpyxl` | Excel datasources |
| `db` | `sqlalchemy` | Non-SQLite databases |
| `neo4j` | `neo4j` driver | Exporting/importing the DVM from Neo4j |
| `dev` | `pytest`, `fakeredis` | Running the test suite |

### 1. Install the Python package

```powershell
pip install -e ".[dev,excel]"
```

### 2. Start Redis

```powershell
# Docker
docker run -d -p 6379:6379 redis:7-alpine

# or natively if installed
redis-server
```

### 3. Start Neo4j

```powershell
docker run -d -p 7474:7474 -p 7687:7687 --name neo4j `
  -e NEO4J_AUTH=neo4j/12345678 `
  neo4j:5
```

Or use [Neo4j Desktop](https://neo4j.com/download/). Default credentials: `neo4j` / `12345678`.

### 4. Load the sample DVM graph into Neo4j (once)

```powershell
datamingler load-neo4j examples\sample.dvm.xml --reset
```

### 5. Start the Python backend

```powershell
datamingler serve examples\datasources.xml
```

### 6. Start the Next.js frontend (second terminal)

```powershell
cd frontend
npm install   # first time only
npm run dev
```

Open **http://localhost:3000**.

---

## Command-line interface

All features are also available via the `datamingler` CLI.

### Evaluate a query

```powershell
datamingler eval `
  examples\sample.dvm.xml `
  examples\datasources.xml `
  examples\customer_summary.qdvm `
  --format json
```

Output formats: `json` (default) or `csv`.

### Inspect a DVM graph

```powershell
datamingler inspect examples\sample.dvm.xml
```

### Parse a text query to XML

```powershell
datamingler parse-query examples\customer_summary.qdvm `
  --output examples\customer_summary.xml
```

### Manage datasources

```powershell
# List
datamingler list-datasources examples\datasources.xml

# Add a CSV source
datamingler add-datasource examples\datasources.xml `
  --name orders_csv --type csv `
  --option path=. --option filename=orders.csv `
  --option delimiter=, --option headings=yes

# Remove
datamingler remove-datasource examples\datasources.xml --name orders_csv
```

### Neo4j compatibility (optional)

```powershell
# Export DVM to Neo4j
datamingler load-neo4j examples\sample.dvm.xml --reset

# Import DVM from Neo4j back to XML
datamingler save-neo4j --output exported.dvm.xml

# Clear the Neo4j graph
datamingler delete-neo4j
```

Neo4j defaults: `bolt://localhost:7687`, user `neo4j`, password `12345678`.
Override with `--uri`, `--user`, `--password`.

---

## HTTP API reference

All endpoints are served by `datamingler serve`.

### DVM graph

| Method | Path | Body / params | Response |
|--------|------|---------------|----------|
| `GET` | `/dvm` | — | Full graph as JSON (`nodes`, `edges` arrays) |
| `POST` | `/dvm/edge` | JSON edge object | `{"ok": true}` |
| `PUT` | `/dvm/edge` | JSON with `head`, `tail`, and fields to update (`selected`, `datasource`, `query`, `description`) | `{"ok": true}` |
| `DELETE` | `/dvm/edge?head=X&tail=Y` | query params | `{"removed": N}` |
| `GET` | `/inspect` | — | Node/edge counts and adjacency summary |

### Datasources

| Method | Path | Body / params | Response |
|--------|------|---------------|----------|
| `GET` | `/datasources` | — | Array of datasource objects |
| `POST` | `/datasources` | JSON with `name`, `type`, and type-specific options | `{"ok": true}` |
| `DELETE` | `/datasources/<name>` | path param | `{"removed": true/false}` |

### Query evaluation

| Method | Path | Body | Response |
|--------|------|------|----------|
| `POST` | `/eval` | QDVM query text | JSON records |
| `POST` | `/eval-csv` | QDVM query text | CSV text |

### Browser UI

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Web UI (index.html) |
| `GET` | `/static/<path>` | Static assets (CSS, JS) |

---

## QDVM query syntax

```
define <root-label> on <dvm-node>:
  compute <label> on <dvm-node> transformedby '<transformation-chain>'
  output <label>[, <label>...]
  where <python-boolean-expression>
```

Transformation chain (semicolon-separated):

| Transformation | Syntax | Description |
|---------------|--------|-------------|
| aggregate | `aggregate:min\|max\|sum\|average\|count\|any` | Reduce a list to a single value |
| filter | `filter:<expr using $Label$>` | Keep list items matching a Python boolean |
| map | `map:python,<module>,<expr using $Label$>` | Transform each value with a Python expression |

`where` clause: Python expression evaluated per root key.
Use `$RootLabel$` to refer to the root key value and `$ChildLabel$` for child values.

**Example:**

```
define X on custID:
  compute A on Age transformedby 'aggregate:any'
  compute G on Gender transformedby 'aggregate:any'
  compute N on Comment transformedby 'map:python,,len($N$);aggregate:sum'
  output A,G,N
  where True
```

---

## Running tests

Tests use `fakeredis` (no live Redis required):

```powershell
cd C:\Users\anast\datamingler\datamingler
pytest tests/ -v
```

Or with the stdlib runner:

```powershell
$env:PYTHONPATH = "."
python -m pytest tests/ -v
```

---

## DVM XML format

DVM graphs are stored as XML files with the `<edges>` root element:

```xml
<?xml version='1.0' encoding='utf-8'?>
<edges>
  <edge>
    <headnode>
      <name>custID</name>
      <description></description>
    </headnode>
    <tailnode>
      <name>Age</name>
      <description></description>
    </tailnode>
    <datasource>customers_csv</datasource>
    <query></query>
    <selected>true</selected>
    <key>1</key>
    <value>2</value>
  </edge>
</edges>
```

`key` and `value` are 1-based column positions in the datasource.
`selected` controls which edges are included in JSON/CSV exports.

---

## Datasources XML format

```xml
<?xml version='1.0' encoding='utf-8'?>
<datasources>
  <datasource type="csv">
    <name>customers_csv</name>
    <path>.</path>
    <filename>customers.csv</filename>
    <delimiter>,</delimiter>
    <headings>yes</headings>
  </datasource>
</datasources>
```

Supported `type` values: `csv`, `excel`, `db`, `process`.

---

## Project layout

```
datamingler/
├── datamingler/              Python package
│   ├── models.py             Frozen dataclasses (DVMEdge, QueryPlan, …)
│   ├── graph.py              DVMGraph — in-memory DVM graph
│   ├── sources.py            DataSourceRegistry + EdgeMaterializer
│   ├── kvstore.py            KeyListStore (Redis-backed, same key layout as Java)
│   ├── engine.py             QueryEvaluator — materialise, transform, export
│   ├── operators.py          aggregate / filter / map / theta-select
│   ├── xmlio.py              DVM XML, datasources XML, query XML & text parser
│   ├── neo4j_adapter.py      Optional Neo4j compatibility
│   ├── server.py             Stdlib HTTP server (no external framework)
│   └── cli.py                datamingler command-line interface
├── frontend/                 Next.js + React web UI
│   ├── .env.local            PYTHON_API_URL=http://localhost:8080
│   ├── next.config.js        Rewrites /api/* → Python server
│   ├── package.json
│   ├── tailwind.config.ts
│   └── src/
│       ├── app/
│       │   ├── globals.css   Tailwind base + component utilities
│       │   ├── layout.tsx    HTML shell
│       │   └── page.tsx      Loads MainApp (ssr: false for Cytoscape)
│       ├── lib/
│       │   ├── api.ts        All fetch calls to /api/*
│       │   └── types.ts      TypeScript interfaces
│       └── components/
│           ├── MainApp.tsx           Tab shell ('use client')
│           ├── Navbar.tsx
│           ├── DVMCanvas.tsx         Cytoscape graph
│           ├── EdgeSidebar.tsx       Edge details panel
│           ├── AddEdgeModal.tsx      Add-edge form modal
│           ├── QueryBuilder.tsx      QDVM editor + results
│           ├── Datasources.tsx       Datasource table
│           └── AddDatasourceModal.tsx
├── examples/
│   ├── sample.dvm.xml
│   ├── datasources.xml
│   ├── customers.csv
│   ├── customer_summary.qdvm
│   └── transactions_after_2019.qdvm
├── tests/
│   └── test_core.py
└── pyproject.toml
```
