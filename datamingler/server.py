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
import re
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
_PROJECTS_DIR: str = "projects"
_DEFAULT_PROJECT_ID: str = "default"
_REDIS_HOST:     str = "127.0.0.1"
_REDIS_PORT:     int = 6379
_STATIC_DIR: Path = Path(__file__).parent / "static"

_UPDATABLE_EDGE_FIELDS = {"selected", "datasource", "query", "description"}
_SAFE_UPLOAD_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


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
        project_id, project_path = self._project_route(path)

        if path in ("", "/"):
            self._serve_file(_STATIC_DIR / "index.html")
        elif path.startswith("/static/"):
            self._serve_file(_STATIC_DIR / path[len("/static/"):])
        elif path == "/projects":
            self._respond_projects()
        elif project_path == "":
            self._respond_project(project_id)
        elif path == "/dvm":
            self._respond_dvm(_DEFAULT_PROJECT_ID)
        elif project_path == "/dvm":
            self._respond_dvm(project_id)
        elif path == "/inspect":
            self._respond_inspect(_DEFAULT_PROJECT_ID)
        elif project_path == "/inspect":
            self._respond_inspect(project_id)
        elif path == "/datasources":
            self._respond_datasources(_DEFAULT_PROJECT_ID)
        elif project_path == "/datasources":
            self._respond_datasources(project_id)
        elif path == "/agent-sessions":
            self._respond_agent_sessions(_DEFAULT_PROJECT_ID)
        elif project_path == "/agent-sessions":
            self._respond_agent_sessions(project_id)
        elif path.startswith("/agent-sessions/"):
            self._respond_agent_session(_DEFAULT_PROJECT_ID, path[len("/agent-sessions/"):])
        elif project_path and project_path.startswith("/agent-sessions/"):
            self._respond_agent_session(project_id, project_path[len("/agent-sessions/"):])
        else:
            self._send_error(404, f"Not found: {self.path}")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        project_id, project_path = self._project_route(path)

        if project_path == "/files":
            self._handle_upload_file(project_id, parsed.query)
            return

        body = self._read_body()

        if path == "/projects":
            self._handle_add_project(body)
        elif path == "/agent-sessions":
            self._handle_create_agent_session(_DEFAULT_PROJECT_ID, body)
        elif project_path == "/agent-sessions":
            self._handle_create_agent_session(project_id, body)
        elif path.startswith("/agent-sessions/") and path.endswith("/messages"):
            session_id = path[len("/agent-sessions/"):-len("/messages")].strip("/")
            self._handle_agent_session_message(_DEFAULT_PROJECT_ID, session_id, body)
        elif project_path and project_path.startswith("/agent-sessions/") and project_path.endswith("/messages"):
            session_id = project_path[len("/agent-sessions/"):-len("/messages")].strip("/")
            self._handle_agent_session_message(project_id, session_id, body)
        elif path == "/eval":
            self._respond_eval(_DEFAULT_PROJECT_ID, body, fmt="json")
        elif project_path == "/eval":
            self._respond_eval(project_id, body, fmt="json")
        elif path == "/eval-csv":
            self._respond_eval(_DEFAULT_PROJECT_ID, body, fmt="csv")
        elif project_path == "/eval-csv":
            self._respond_eval(project_id, body, fmt="csv")
        elif path == "/query/agent":
            self._handle_query_agent(_DEFAULT_PROJECT_ID, body)
        elif project_path == "/query/agent":
            self._handle_query_agent(project_id, body)
        elif path == "/dvm/edge":
            self._handle_add_edge(_DEFAULT_PROJECT_ID, body)
        elif project_path == "/dvm/edge":
            self._handle_add_edge(project_id, body)
        elif path == "/datasources":
            self._handle_add_datasource(_DEFAULT_PROJECT_ID, body)
        elif project_path == "/datasources":
            self._handle_add_datasource(project_id, body)
        else:
            self._send_error(404, f"Not found: {self.path}")

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        project_id, project_path = self._project_route(path)
        body = self._read_body()

        if path == "/dvm/edge":
            self._handle_update_edge(_DEFAULT_PROJECT_ID, body)
        elif project_path == "/dvm/edge":
            self._handle_update_edge(project_id, body)
        else:
            self._send_error(404, f"Not found: {self.path}")

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        project_id, project_path = self._project_route(path)
        params = parse_qs(parsed.query)

        if path == "/dvm/edge":
            self._handle_delete_edge(
                _DEFAULT_PROJECT_ID,
                params.get("head", [""])[0],
                params.get("tail", [""])[0],
            )
        elif project_path == "/dvm/edge":
            self._handle_delete_edge(
                project_id,
                params.get("head", [""])[0],
                params.get("tail", [""])[0],
            )
        elif path.startswith("/datasources/"):
            self._handle_delete_datasource(_DEFAULT_PROJECT_ID, path[len("/datasources/"):])
        elif project_path and project_path.startswith("/datasources/"):
            self._handle_delete_datasource(project_id, project_path[len("/datasources/"):])
        else:
            self._send_error(404, f"Not found: {self.path}")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _read_body(self) -> str:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length).decode("utf-8") if length else ""

    def _read_bytes(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

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

    def _project_route(self, path: str) -> tuple[str | None, str | None]:
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "projects":
            return parts[1], "/" + "/".join(parts[2:]) if len(parts) > 2 else ""
        return None, None

    def _project_store(self):
        from .projects import ProjectStore

        return ProjectStore(_PROJECTS_DIR)

    def _datasources_xml(self, project_id: str) -> str:
        return str(self._project_store().datasources_xml(project_id))

    def _agent_sessions(self):
        from .agent_sessions import AgentSessionStore

        return AgentSessionStore(self._project_store())

    # ------------------------------------------------------------------
    # GET handlers — DVM reads from Neo4j
    # ------------------------------------------------------------------

    def _respond_projects(self) -> None:
        try:
            self._send_json([project.__dict__ for project in self._project_store().list_projects()])
        except Exception:
            self._send_error(500, traceback.format_exc())

    def _respond_project(self, project_id: str) -> None:
        try:
            self._send_json(self._project_store().get(project_id).__dict__)
        except KeyError as exc:
            self._send_error(404, str(exc))
        except Exception:
            self._send_error(500, traceback.format_exc())

    def _respond_dvm(self, project_id: str) -> None:
        try:
            from .models import positions_to_text
            from .neo4j_adapter import read_graph_from_neo4j

            graph = read_graph_from_neo4j(project_id=project_id, **self._neo4j_kwargs())
            self._send_json({
                "project_id": project_id,
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

    def _respond_inspect(self, project_id: str) -> None:
        try:
            from .neo4j_adapter import read_graph_from_neo4j

            graph = read_graph_from_neo4j(project_id=project_id, **self._neo4j_kwargs())
            self._send_json({
                "project_id": project_id,
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

    def _respond_datasources(self, project_id: str) -> None:
        try:
            from .xmlio import load_datasources_xml

            datasources = load_datasources_xml(self._datasources_xml(project_id))
            self._send_json([
                {"name": ds.name, "type": ds.type, **ds.options}
                for ds in datasources.values()
            ])
        except Exception:
            self._send_error(500, traceback.format_exc())

    def _respond_agent_sessions(self, project_id: str) -> None:
        try:
            from .agent_sessions import session_to_dict

            self._send_json([
                session_to_dict(session, include_messages=False)
                for session in self._agent_sessions().list(project_id)
            ])
        except Exception:
            self._send_error(500, traceback.format_exc())

    def _respond_agent_session(self, project_id: str, session_id: str) -> None:
        try:
            from .agent_sessions import session_to_dict

            session = self._agent_sessions().get(project_id, session_id)
            self._send_json(session_to_dict(session))
        except KeyError as exc:
            self._send_error(404, str(exc))
        except ValueError as exc:
            self._send_error(400, str(exc))
        except Exception:
            self._send_error(500, traceback.format_exc())

    # ------------------------------------------------------------------
    # POST handlers
    # ------------------------------------------------------------------

    def _respond_eval(self, project_id: str, query_text: str, fmt: str) -> None:
        try:
            from .engine import QueryEvaluator
            from .neo4j_adapter import read_graph_from_neo4j
            from .sources import DataSourceRegistry
            from .xmlio import parse_query_text

            from .kvstore import KeyListStore

            graph = read_graph_from_neo4j(project_id=project_id, **self._neo4j_kwargs())
            registry = DataSourceRegistry.from_xml(self._datasources_xml(project_id))
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

    def _handle_add_project(self, body: str) -> None:
        try:
            data = json.loads(body)
            project = self._project_store().create(
                str(data.get("id", "")),
                str(data.get("name", "")),
                description=str(data.get("description", "")),
            )
            self._send_json(project.__dict__)
        except ValueError as exc:
            self._send_error(400, str(exc))
        except Exception:
            self._send_error(500, traceback.format_exc())

    def _handle_create_agent_session(self, project_id: str, body: str) -> None:
        try:
            from .agent_sessions import session_to_dict

            data = json.loads(body or "{}")
            session = self._agent_sessions().create(
                project_id,
                title=str(data.get("title", "")),
                provider=str(data.get("provider", "openai")),
                model=str(data.get("model", "gpt-5.1")),
            )
            self._send_json(session_to_dict(session))
        except ValueError as exc:
            self._send_error(400, str(exc))
        except Exception:
            self._send_error(500, traceback.format_exc())

    def _handle_agent_session_message(self, project_id: str, session_id: str, body: str) -> None:
        try:
            from .agent_sessions import session_to_dict
            from .llm_query_agent import response_to_dict

            data = json.loads(body)
            prompt = str(data.get("prompt", ""))
            provider = str(data.get("provider") or "openai")
            model = str(data.get("model") or "")
            if not prompt.strip():
                raise ValueError("prompt is required")
            if not model.strip():
                raise ValueError("model is required")

            store = self._agent_sessions()
            session = store.append_user_message(project_id, session_id, prompt, provider=provider, model=model)
            history = [
                {"role": message.role, "content": message.content}
                for message in session.messages[:-1]
                if message.role in {"user", "assistant"}
            ]
            response = self._run_agent_for_prompt(project_id, prompt, provider, model, history)
            response_dict = response_to_dict(response)
            updated = store.append_assistant_message(
                project_id,
                session_id,
                response.answer,
                provider=provider,
                model=model,
                steps=response_dict["steps"],
                queries=response_dict["queries"],
            )
            self._send_json(session_to_dict(updated))
        except ValueError as exc:
            self._send_error(400, str(exc))
        except RuntimeError as exc:
            self._send_error(400, str(exc))
        except KeyError as exc:
            self._send_error(404, str(exc))
        except Exception:
            self._send_error(500, traceback.format_exc())

    def _handle_query_agent(self, project_id: str, body: str) -> None:
        try:
            from .llm_query_agent import response_to_dict, run_query_agent

            data = json.loads(body)
            prompt = str(data.get("prompt", ""))
            provider = str(data.get("provider") or "openai")
            model = str(data.get("model") or "")
            if not model:
                raise ValueError("model is required")
            response = self._run_agent_for_prompt(project_id, prompt, provider, model, [])
            self._send_json(response_to_dict(response))
        except ValueError as exc:
            self._send_error(400, str(exc))
        except RuntimeError as exc:
            self._send_error(400, str(exc))
        except Exception:
            self._send_error(500, traceback.format_exc())

    def _run_agent_for_prompt(
        self,
        project_id: str,
        prompt: str,
        provider: str,
        model: str,
        history: list[dict[str, str]],
    ):
        from .engine import QueryEvaluator
        from .kvstore import KeyListStore
        from .llm_query_agent import run_query_agent
        from .neo4j_adapter import read_graph_from_neo4j
        from .sources import DataSourceRegistry
        from .xmlio import parse_query_text

        graph = read_graph_from_neo4j(project_id=project_id, **self._neo4j_kwargs())
        registry = DataSourceRegistry.from_xml(self._datasources_xml(project_id))

        def evaluate_query(query_text: str) -> str:
            plan = parse_query_text(query_text)
            store = KeyListStore(host=_REDIS_HOST, port=_REDIS_PORT)
            result = QueryEvaluator(graph, registry, store=store).evaluate(plan)
            return json.dumps(result.to_json_records(), indent=2)

        return run_query_agent(
            prompt,
            graph,
            provider=provider,  # type: ignore[arg-type]
            model=model,
            evaluate_query=evaluate_query,
            history=history,
        )

    def _handle_add_edge(self, project_id: str, body: str) -> None:
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
            add_edge_to_neo4j(edge, project_id=project_id, **self._neo4j_kwargs())
            self._send_json({"ok": True})
        except Exception:
            self._send_error(500, traceback.format_exc())

    def _handle_add_datasource(self, project_id: str, body: str) -> None:
        try:
            from .datasource_inference import infer_edges_for_datasource
            from .models import DataSource
            from .neo4j_adapter import add_edge_to_neo4j
            from .xmlio import add_datasource_to_xml

            data = json.loads(body)
            name = data.pop("name", "")
            ds_type = data.pop("type", "")
            datasource = DataSource(name=name, type=ds_type, options=data)
            datasources_xml = self._datasources_xml(project_id)
            add_datasource_to_xml(datasources_xml, datasource)

            inferred_edges = []
            inference_warning = ""
            try:
                inferred_edges = infer_edges_for_datasource(datasource, base_dir=Path(datasources_xml).parent)
                for edge in inferred_edges:
                    add_edge_to_neo4j(edge, project_id=project_id, **self._neo4j_kwargs())
            except Exception as exc:
                inference_warning = str(exc)

            self._send_json({
                "ok": True,
                "inferred_edges": len(inferred_edges),
                "inference_warning": inference_warning,
            })
        except Exception:
            self._send_error(500, traceback.format_exc())

    def _handle_upload_file(self, project_id: str, query: str) -> None:
        try:
            params = parse_qs(query)
            filename = _safe_upload_filename(params.get("filename", [""])[0])
            if not filename:
                self._send_error(400, "filename is required")
                return

            upload_dir = self._project_store().project_dir(project_id) / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            target = _unique_upload_path(upload_dir / filename)
            target.write_bytes(self._read_bytes())

            self._send_json({"path": "uploads", "filename": target.name})
        except ValueError as exc:
            self._send_error(400, str(exc))
        except Exception:
            self._send_error(500, traceback.format_exc())

    # ------------------------------------------------------------------
    # PUT handlers
    # ------------------------------------------------------------------

    def _handle_update_edge(self, project_id: str, body: str) -> None:
        try:
            from .neo4j_adapter import update_edge_in_neo4j

            data = json.loads(body)
            head = data["head"].strip()
            tail = data["tail"].strip()
            updates = {k: v for k, v in data.items() if k in _UPDATABLE_EDGE_FIELDS}
            update_edge_in_neo4j(head, tail, updates, project_id=project_id, **self._neo4j_kwargs())
            self._send_json({"ok": True})
        except Exception:
            self._send_error(500, traceback.format_exc())

    # ------------------------------------------------------------------
    # DELETE handlers
    # ------------------------------------------------------------------

    def _handle_delete_edge(self, project_id: str, head: str, tail: str) -> None:
        try:
            from .neo4j_adapter import remove_edge_from_neo4j

            count = remove_edge_from_neo4j(head, tail, project_id=project_id, **self._neo4j_kwargs())
            self._send_json({"removed": count})
        except Exception:
            self._send_error(500, traceback.format_exc())

    def _handle_delete_datasource(self, project_id: str, name: str) -> None:
        try:
            from .xmlio import remove_datasource_from_xml

            removed = remove_datasource_from_xml(self._datasources_xml(project_id), name)
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
    projects_dir: str = "projects",
    default_project_id: str = "default",
    host: str = "localhost",
    port: int = 8080,
) -> None:
    """Start the DataMingler HTTP server (blocking).

    The DVM graph is read from / written to Neo4j on every request.
    ``datasources_xml`` is the only file path required at startup.
    """
    global _NEO4J_URI, _NEO4J_USER, _NEO4J_PASSWORD, _DATASOURCES_XML, _PROJECTS_DIR, _DEFAULT_PROJECT_ID, _REDIS_HOST, _REDIS_PORT
    _NEO4J_URI      = neo4j_uri
    _NEO4J_USER     = neo4j_user
    _NEO4J_PASSWORD = neo4j_password
    _DATASOURCES_XML = str(Path(datasources_xml).resolve())
    _PROJECTS_DIR = str(Path(projects_dir).resolve())
    _DEFAULT_PROJECT_ID = default_project_id
    _REDIS_HOST     = redis_host
    _REDIS_PORT     = redis_port

    from .projects import ProjectStore

    store = ProjectStore(_PROJECTS_DIR)
    if default_project_id == "default":
        store.ensure_default(_DATASOURCES_XML)
    elif not store.exists(default_project_id):
        store.create(default_project_id, default_project_id, datasources_template=_DATASOURCES_XML)

    server = HTTPServer((host, port), _Handler)
    print(f"DataMingler server running on http://{host}:{port}/")
    print(f"  Neo4j:       {neo4j_uri}  (user: {neo4j_user})")
    print(f"  Projects:    {_PROJECTS_DIR}  (default: {_DEFAULT_PROJECT_ID})")
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


def _safe_upload_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    return _SAFE_UPLOAD_NAME_RE.sub("_", name)


def _unique_upload_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(1, 10_000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise ValueError(f"Could not find an available upload filename for {path.name!r}")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(prog="datamingler.server")
    p.add_argument("--datasources", required=True, help="Path to datasources XML file")
    p.add_argument("--neo4j-uri",      default="bolt://localhost:7687")
    p.add_argument("--neo4j-user",     default="neo4j")
    p.add_argument("--neo4j-password", default="12345678")
    p.add_argument("--redis-host",     default="127.0.0.1")
    p.add_argument("--redis-port",     type=int, default=6379)
    p.add_argument("--projects-dir",   default="projects")
    p.add_argument("--default-project-id", default="default")
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
        projects_dir=a.projects_dir,
        default_project_id=a.default_project_id,
        host=a.host,
        port=a.port,
    )
