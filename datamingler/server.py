"""Minimal HTTP server — DataMingler engine over HTTP.

The DVM graph is read from and written to Neo4j on every request.
Datasources are still loaded from a local XML file.

Endpoints:
    GET  /                         browser UI (index.html)
    GET  /static/<path>            static assets
    GET  /dvm                      full DVM graph JSON       (reads Neo4j)
    POST /dvm/edge                 add a DVM edge            (writes Neo4j)
    PUT  /dvm/edge                 update a DVM edge         (writes Neo4j)
    DELETE /dvm/edge?head=X&tail=Y remove DVM edge(s)        (writes Neo4j)
    GET  /inspect                  DVM summary               (reads Neo4j)
    GET  /datasources              list datasources          (reads XML)
    POST /datasources              add a datasource          (writes XML)
    DELETE /datasources/<name>     remove a datasource       (writes XML)
    POST /eval                     evaluate query → JSON     (reads Neo4j + XML)
    POST /eval-csv                 evaluate query → CSV      (reads Neo4j + XML)

Start with:
    datamingler serve --datasources path/to/datasources.xml
or:
    python -m datamingler.server --datasources path/to/datasources.xml
"""
from __future__ import annotations

import json
import mimetypes
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

# ── Module-level configuration set by serve() ──────────────────────────────
_NEO4J_URI:      str = "bolt://localhost:7687"
_NEO4J_USER:     str = "neo4j"
_NEO4J_PASSWORD: str = "12345678"
_DATASOURCES_XML: str = ""
_REDIS_HOST:     str = "127.0.0.1"
_REDIS_PORT:     int = 6379
_STATIC_DIR: Path = Path(__file__).parent / "static"

_UPDATABLE_EDGE_FIELDS = {"selected", "datasource", "query", "description"}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        pass

    def _add_cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._add_cors()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path in ("", "/"):
            self._serve_file(_STATIC_DIR / "index.html")
        elif path.startswith("/static/"):
            self._serve_file(_STATIC_DIR / path[len("/static/"):])
        elif path == "/dvm":
            self._respond_dvm()
        elif path == "/inspect":
            self._respond_inspect()
        elif path == "/datasources":
            self._respond_datasources()
        else:
            self._send_error(404, f"Not found: {self.path}")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        body = self._read_body()

        if path == "/eval":
            self._respond_eval(body, fmt="json")
        elif path == "/eval-csv":
            self._respond_eval(body, fmt="csv")
        elif path == "/dvm/edge":
            self._handle_add_edge(body)
        elif path == "/datasources":
            self._handle_add_datasource(body)
        else:
            self._send_error(404, f"Not found: {self.path}")

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        body = self._read_body()

        if path == "/dvm/edge":
            self._handle_update_edge(body)
        else:
            self._send_error(404, f"Not found: {self.path}")

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        if path == "/dvm/edge":
            self._handle_delete_edge(
                params.get("head", [""])[0],
                params.get("tail", [""])[0],
            )
        elif path.startswith("/datasources/"):
            self._handle_delete_datasource(path[len("/datasources/"):])
        else:
            self._send_error(404, f"Not found: {self.path}")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _read_body(self) -> str:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length).decode("utf-8") if length else ""

    def _serve_file(self, full: Path) -> None:
        if not full.exists() or not full.is_file():
            self._send_error(404, f"File not found: {full.name}")
            return
        content_type, _ = mimetypes.guess_type(str(full))
        self._send_response(200, content_type or "application/octet-stream", full.read_bytes())

    def _send_json(self, data: Any) -> None:
        self._send_response(200, "application/json", json.dumps(data, indent=2).encode())

    def _send_response(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._add_cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str) -> None:
        self._send_response(status, "text/plain", message.encode())

    def _neo4j_kwargs(self) -> dict:
        return {"uri": _NEO4J_URI, "user": _NEO4J_USER, "password": _NEO4J_PASSWORD}

    # ------------------------------------------------------------------
    # GET handlers — DVM reads from Neo4j
    # ------------------------------------------------------------------

    def _respond_dvm(self) -> None:
        try:
            from .models import positions_to_text
            from .neo4j_adapter import read_graph_from_neo4j

            graph = read_graph_from_neo4j(**self._neo4j_kwargs())
            self._send_json({
                "nodes": [
                    {"name": n.name, "description": n.description}
                    for n in graph.nodes.values()
                ],
                "edges": [
                    {
                        "head": e.head_name,
                        "tail": e.tail_name,
                        "head_description": e.head.description,
                        "tail_description": e.tail.description,
                        "datasource": e.datasource,
                        "query": e.query,
                        "key": positions_to_text(e.key_positions),
                        "value": positions_to_text(e.value_positions),
                        "selected": e.selected,
                        "description": e.description,
                    }
                    for e in graph.edges
                ],
            })
        except Exception:
            self._send_error(500, traceback.format_exc())

    def _respond_inspect(self) -> None:
        try:
            from .neo4j_adapter import read_graph_from_neo4j

            graph = read_graph_from_neo4j(**self._neo4j_kwargs())
            self._send_json({
                "nodes": len(graph.nodes),
                "edges": len(graph.edges),
                "adjacency": {
                    name: graph.children(name)
                    for name in sorted(graph.nodes)
                    if graph.children(name)
                },
            })
        except Exception:
            self._send_error(500, traceback.format_exc())

    def _respond_datasources(self) -> None:
        try:
            from .xmlio import load_datasources_xml

            datasources = load_datasources_xml(_DATASOURCES_XML)
            self._send_json([
                {"name": ds.name, "type": ds.type, **ds.options}
                for ds in datasources.values()
            ])
        except Exception:
            self._send_error(500, traceback.format_exc())

    # ------------------------------------------------------------------
    # POST handlers
    # ------------------------------------------------------------------

    def _respond_eval(self, query_text: str, fmt: str) -> None:
        try:
            from .engine import QueryEvaluator
            from .neo4j_adapter import read_graph_from_neo4j
            from .sources import DataSourceRegistry
            from .xmlio import parse_query_text

            from .kvstore import KeyListStore

            graph = read_graph_from_neo4j(**self._neo4j_kwargs())
            registry = DataSourceRegistry.from_xml(_DATASOURCES_XML)
            plan = parse_query_text(query_text)
            store = KeyListStore(host=_REDIS_HOST, port=_REDIS_PORT)
            result = QueryEvaluator(graph, registry, store=store).evaluate(plan)

            if fmt == "csv":
                rows = result.to_rows()
                if not rows:
                    payload = b""
                else:
                    import csv
                    import io
                    buf = io.StringIO()
                    writer = csv.DictWriter(buf, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
                    payload = buf.getvalue().encode("utf-8")
                self._send_response(200, "text/csv", payload)
            else:
                payload = json.dumps(result.to_json_records(), indent=2).encode("utf-8")
                self._send_response(200, "application/json", payload)
        except Exception:
            self._send_error(500, traceback.format_exc())

    def _handle_add_edge(self, body: str) -> None:
        try:
            from .models import DVMEdge
            from .neo4j_adapter import add_edge_to_neo4j

            data = json.loads(body)
            edge = DVMEdge.create(
                head_name=data["head"],
                tail_name=data["tail"],
                datasource=data.get("datasource", ""),
                head_description=data.get("head_description", ""),
                tail_description=data.get("tail_description", ""),
                query=data.get("query", ""),
                key_positions=data.get("key", ""),
                value_positions=data.get("value", ""),
                selected=bool(data.get("selected", False)),
            )
            add_edge_to_neo4j(edge, **self._neo4j_kwargs())
            self._send_json({"ok": True})
        except Exception:
            self._send_error(500, traceback.format_exc())

    def _handle_add_datasource(self, body: str) -> None:
        try:
            from .models import DataSource
            from .xmlio import add_datasource_to_xml

            data = json.loads(body)
            name = data.pop("name", "")
            ds_type = data.pop("type", "")
            add_datasource_to_xml(_DATASOURCES_XML, DataSource(name=name, type=ds_type, options=data))
            self._send_json({"ok": True})
        except Exception:
            self._send_error(500, traceback.format_exc())

    # ------------------------------------------------------------------
    # PUT handlers
    # ------------------------------------------------------------------

    def _handle_update_edge(self, body: str) -> None:
        try:
            from .neo4j_adapter import update_edge_in_neo4j

            data = json.loads(body)
            head = data["head"].strip()
            tail = data["tail"].strip()
            updates = {k: v for k, v in data.items() if k in _UPDATABLE_EDGE_FIELDS}
            update_edge_in_neo4j(head, tail, updates, **self._neo4j_kwargs())
            self._send_json({"ok": True})
        except Exception:
            self._send_error(500, traceback.format_exc())

    # ------------------------------------------------------------------
    # DELETE handlers
    # ------------------------------------------------------------------

    def _handle_delete_edge(self, head: str, tail: str) -> None:
        try:
            from .neo4j_adapter import remove_edge_from_neo4j

            count = remove_edge_from_neo4j(head, tail, **self._neo4j_kwargs())
            self._send_json({"removed": count})
        except Exception:
            self._send_error(500, traceback.format_exc())

    def _handle_delete_datasource(self, name: str) -> None:
        try:
            from .xmlio import remove_datasource_from_xml

            removed = remove_datasource_from_xml(_DATASOURCES_XML, name)
            self._send_json({"removed": removed})
        except Exception:
            self._send_error(500, traceback.format_exc())


def serve(
    datasources_xml: str,
    *,
    neo4j_uri: str = "bolt://localhost:7687",
    neo4j_user: str = "neo4j",
    neo4j_password: str = "12345678",
    redis_host: str = "127.0.0.1",
    redis_port: int = 6379,
    host: str = "localhost",
    port: int = 8080,
) -> None:
    """Start the DataMingler HTTP server (blocking).

    The DVM graph is read from / written to Neo4j on every request.
    ``datasources_xml`` is the only file path required at startup.
    """
    global _NEO4J_URI, _NEO4J_USER, _NEO4J_PASSWORD, _DATASOURCES_XML, _REDIS_HOST, _REDIS_PORT
    _NEO4J_URI      = neo4j_uri
    _NEO4J_USER     = neo4j_user
    _NEO4J_PASSWORD = neo4j_password
    _DATASOURCES_XML = str(Path(datasources_xml).resolve())
    _REDIS_HOST     = redis_host
    _REDIS_PORT     = redis_port

    server = HTTPServer((host, port), _Handler)
    print(f"DataMingler server running on http://{host}:{port}/")
    print(f"  Neo4j:       {neo4j_uri}  (user: {neo4j_user})")
    print(f"  Datasources: {_DATASOURCES_XML}")
    print("  Endpoints:")
    print("    GET  /                      web UI")
    print("    GET  /dvm                   DVM graph (Neo4j)")
    print("    POST /dvm/edge              add edge (Neo4j)")
    print("    PUT  /dvm/edge              update edge (Neo4j)")
    print("    DELETE /dvm/edge            remove edge (Neo4j)")
    print("    GET  /datasources           list datasources (XML)")
    print("    POST /datasources           add datasource (XML)")
    print("    DELETE /datasources/<name>  remove datasource (XML)")
    print("    POST /eval                  evaluate query → JSON")
    print("    POST /eval-csv              evaluate query → CSV")
    print("    GET  /inspect               DVM summary")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nserver stopped")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(prog="datamingler.server")
    p.add_argument("--datasources", required=True, help="Path to datasources XML file")
    p.add_argument("--neo4j-uri",      default="bolt://localhost:7687")
    p.add_argument("--neo4j-user",     default="neo4j")
    p.add_argument("--neo4j-password", default="12345678")
    p.add_argument("--redis-host",     default="127.0.0.1")
    p.add_argument("--redis-port",     type=int, default=6379)
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=8080)
    a = p.parse_args()
    serve(
        a.datasources,
        neo4j_uri=a.neo4j_uri,
        neo4j_user=a.neo4j_user,
        neo4j_password=a.neo4j_password,
        redis_host=a.redis_host,
        redis_port=a.redis_port,
        host=a.host,
        port=a.port,
    )
