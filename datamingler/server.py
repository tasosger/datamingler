"""Minimal HTTP server exposing the DataMingler engine over HTTP.

Mirrors the endpoints provided by the original PHP/Java web interface:
  - POST /eval     → run a query and return JSON   (createAPI.php)
  - POST /eval-csv → run a query and return CSV    (runquery.php)
  - GET  /inspect  → summarise a DVM graph         (datamingler.php list view)
  - GET  /datasources → list datasources           (datamingler.php)

The server is intentionally dependency-free (stdlib only).  Start it with:

    python -m datamingler.server --dvm path/to/dvm.xml \\
                                 --datasources path/to/datasources.xml

or via the CLI:

    datamingler serve --dvm ... --datasources ...
"""
from __future__ import annotations

import json
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


# Module-level state set by _make_handler / serve()
_DVM_XML: str = ""
_DATASOURCES_XML: str = ""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # silence default logging
        pass

    # ------------------------------------------------------------------
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/inspect":
            self._respond_inspect()
        elif path == "/datasources":
            self._respond_datasources()
        else:
            self._send_error(404, f"Not found: {self.path}")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else ""

        if path == "/eval":
            self._respond_eval(body, fmt="json")
        elif path == "/eval-csv":
            self._respond_eval(body, fmt="csv")
        else:
            self._send_error(404, f"Not found: {self.path}")

    # ------------------------------------------------------------------
    def _respond_eval(self, query_text: str, fmt: str) -> None:
        try:
            from .engine import QueryEvaluator
            from .sources import DataSourceRegistry
            from .xmlio import load_dvm_xml, parse_query_text

            graph = load_dvm_xml(_DVM_XML)
            registry = DataSourceRegistry.from_xml(_DATASOURCES_XML)
            plan = parse_query_text(query_text)
            result = QueryEvaluator(graph, registry).evaluate(plan)

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

    def _respond_inspect(self) -> None:
        try:
            from .xmlio import load_dvm_xml

            graph = load_dvm_xml(_DVM_XML)
            info: dict[str, Any] = {
                "nodes": len(graph.nodes),
                "edges": len(graph.edges),
                "adjacency": {
                    name: graph.children(name)
                    for name in sorted(graph.nodes)
                    if graph.children(name)
                },
            }
            payload = json.dumps(info, indent=2).encode("utf-8")
            self._send_response(200, "application/json", payload)
        except Exception:
            self._send_error(500, traceback.format_exc())

    def _respond_datasources(self) -> None:
        try:
            from .xmlio import load_datasources_xml

            datasources = load_datasources_xml(_DATASOURCES_XML)
            info = [
                {"name": ds.name, "type": ds.type, **ds.options}
                for ds in datasources.values()
            ]
            payload = json.dumps(info, indent=2).encode("utf-8")
            self._send_response(200, "application/json", payload)
        except Exception:
            self._send_error(500, traceback.format_exc())

    # ------------------------------------------------------------------
    def _send_response(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str) -> None:
        body = message.encode("utf-8")
        self._send_response(status, "text/plain", body)


def serve(
    dvm_xml: str,
    datasources_xml: str,
    *,
    host: str = "localhost",
    port: int = 8080,
) -> None:
    """Start the DataMingler HTTP server (blocking)."""
    global _DVM_XML, _DATASOURCES_XML
    _DVM_XML = str(Path(dvm_xml).resolve())
    _DATASOURCES_XML = str(Path(datasources_xml).resolve())

    server = HTTPServer((host, port), _Handler)
    print(f"DataMingler server running on http://{host}:{port}/")
    print(f"  DVM:         {_DVM_XML}")
    print(f"  Datasources: {_DATASOURCES_XML}")
    print("  Endpoints:")
    print("    POST /eval        - evaluate a QDVM text query -> JSON")
    print("    POST /eval-csv    - evaluate a QDVM text query -> CSV")
    print("    GET  /inspect     - DVM graph summary")
    print("    GET  /datasources - list datasources")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nserver stopped")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(prog="datamingler.server")
    p.add_argument("--dvm", required=True)
    p.add_argument("--datasources", required=True)
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=8080)
    a = p.parse_args()
    serve(a.dvm, a.datasources, host=a.host, port=a.port)
