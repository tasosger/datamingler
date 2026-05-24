from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import QueryEvaluator
from .sources import DataSourceRegistry
from .models import DataSource, DVMEdge
from .neo4j_adapter import delete_graph_from_neo4j, load_graph_to_neo4j, read_graph_from_neo4j
from .xmlio import (
    add_datasource_to_xml,
    add_edge_to_dvm_xml,
    load_datasources_xml,
    load_dvm_xml,
    load_query_text,
    load_query_xml,
    remove_datasource_from_xml,
    remove_edge_from_dvm_xml,
    save_datasources_xml,
    save_dvm_xml,
    save_query_xml,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="datamingler")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_query = subparsers.add_parser("parse-query", help="Parse QDVM text into query XML")
    parse_query.add_argument("query")
    parse_query.add_argument("--output", "-o")

    eval_parser = subparsers.add_parser("eval", help="Evaluate a DVM query")
    eval_parser.add_argument("dvm_xml")
    eval_parser.add_argument("datasources_xml")
    eval_parser.add_argument("query")
    eval_parser.add_argument("--query-format", choices=["auto", "text", "xml"], default="auto")
    eval_parser.add_argument("--keys-mode", choices=["all", "intersect"], default="all")
    eval_parser.add_argument("--format", choices=["json", "csv"], default="json")
    eval_parser.add_argument("--output", "-o")

    inspect_parser = subparsers.add_parser("inspect", help="Print a concise DVM summary")
    inspect_parser.add_argument("dvm_xml")

    normalize_parser = subparsers.add_parser("normalize-dvm", help="Rewrite DVM XML in normalized formatting")
    normalize_parser.add_argument("dvm_xml")
    normalize_parser.add_argument("--output", "-o", required=True)

    neo4j_load = subparsers.add_parser("load-neo4j", help="Load DVM XML into Neo4j")
    neo4j_load.add_argument("dvm_xml")
    neo4j_load.add_argument("--uri", default="bolt://localhost:7687")
    neo4j_load.add_argument("--user", default="neo4j")
    neo4j_load.add_argument("--password", default="12345678")
    neo4j_load.add_argument("--reset", action="store_true")

    neo4j_save = subparsers.add_parser("save-neo4j", help="Save Neo4j DVM graph to XML")
    neo4j_save.add_argument("--output", "-o", required=True)
    neo4j_save.add_argument("--uri", default="bolt://localhost:7687")
    neo4j_save.add_argument("--user", default="neo4j")
    neo4j_save.add_argument("--password", default="12345678")

    neo4j_delete = subparsers.add_parser("delete-neo4j", help="Delete all DVM attribute nodes from Neo4j")
    neo4j_delete.add_argument("--uri", default="bolt://localhost:7687")
    neo4j_delete.add_argument("--user", default="neo4j")
    neo4j_delete.add_argument("--password", default="12345678")

    export_json = subparsers.add_parser(
        "export-json",
        help="Export a JSON document from selected DVM edges (no explicit query plan required)",
    )
    export_json.add_argument("dvm_xml")
    export_json.add_argument("datasources_xml")
    export_json.add_argument("root", help="Root DVM node name")
    export_json.add_argument("--keys-mode", choices=["all", "intersect"], default="all")
    export_json.add_argument("--all-edges", action="store_true", default=False,
                             help="Traverse all edges via BFS (ignore selected flag)")
    export_json.add_argument("--output", "-o")

    # --- HTTP server ---
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start the HTTP server — DVM graph is read from/written to Neo4j",
    )
    serve_parser.add_argument("datasources_xml", help="Path to datasources XML file")
    serve_parser.add_argument("--neo4j-uri",      default="bolt://localhost:7687")
    serve_parser.add_argument("--neo4j-user",     default="neo4j")
    serve_parser.add_argument("--neo4j-password", default="12345678")
    serve_parser.add_argument("--host", default="localhost")
    serve_parser.add_argument("--port", type=int, default=8080)

    # --- datasource management (mirrors createSource.php / deleteSource.php) ---
    list_ds = subparsers.add_parser("list-datasources", help="List datasources in a datasources XML file")
    list_ds.add_argument("datasources_xml")

    add_ds = subparsers.add_parser("add-datasource", help="Add a datasource to a datasources XML file")
    add_ds.add_argument("datasources_xml")
    add_ds.add_argument("name")
    add_ds.add_argument("type", choices=["csv", "excel", "db", "process"])
    add_ds.add_argument("options", nargs="*", metavar="KEY=VALUE",
                        help="Datasource options as KEY=VALUE pairs (e.g. filename=data.csv headings=yes)")

    rm_ds = subparsers.add_parser("remove-datasource", help="Remove a datasource from a datasources XML file")
    rm_ds.add_argument("datasources_xml")
    rm_ds.add_argument("name")

    # --- DVM edge management (mirrors createCSVEdgesNeo4j.java / createEdgeNeo4j.java) ---
    add_edge = subparsers.add_parser("add-edge", help="Add an edge to a DVM XML file")
    add_edge.add_argument("dvm_xml")
    add_edge.add_argument("head", help="Head (root) node name")
    add_edge.add_argument("tail", help="Tail (child) node name")
    add_edge.add_argument("datasource", help="Datasource name")
    add_edge.add_argument("--key", default="1", help="Key column position(s), comma-separated (default: 1)")
    add_edge.add_argument("--value", default="2", help="Value column position(s), comma-separated (default: 2)")
    add_edge.add_argument("--query", default="", help="SQL query string (for db datasources)")
    add_edge.add_argument("--head-description", default="")
    add_edge.add_argument("--tail-description", default="")
    add_edge.add_argument("--selected", action="store_true", default=False)
    add_edge.add_argument("--bidirectional", action="store_true", default=False,
                          help="Also add the reverse edge (mirrors createEdgeNeo4j.java behaviour)")

    rm_edge = subparsers.add_parser("remove-edge", help="Remove edge(s) from a DVM XML file")
    rm_edge.add_argument("dvm_xml")
    rm_edge.add_argument("head", help="Head (root) node name")
    rm_edge.add_argument("tail", help="Tail (child) node name")

    args = parser.parse_args(argv)

    if args.command == "parse-query":
        plan = load_query_text(args.query)
        output = args.output or f"{args.query}.xml"
        save_query_xml(plan, output)
        print(output)
        return 0

    if args.command == "eval":
        graph = load_dvm_xml(args.dvm_xml)
        registry = DataSourceRegistry.from_xml(args.datasources_xml)
        plan = _load_plan(args.query, args.query_format)
        result = QueryEvaluator(graph, registry).evaluate(plan, keys_mode=args.keys_mode)
        if args.output:
            if args.format == "json":
                result.write_json(args.output)
            else:
                result.write_csv(args.output)
            print(args.output)
        elif args.format == "json":
            print(json.dumps(result.to_json_records(), indent=2))
        else:
            for row in result.to_rows():
                print(row)
        return 0

    if args.command == "inspect":
        graph = load_dvm_xml(args.dvm_xml)
        print(f"nodes: {len(graph.nodes)}")
        print(f"edges: {len(graph.edges)}")
        for name in sorted(graph.nodes):
            children = graph.children(name)
            if children:
                print(f"{name} -> {', '.join(children)}")
        return 0

    if args.command == "normalize-dvm":
        graph = load_dvm_xml(args.dvm_xml)
        save_dvm_xml(graph, args.output)
        print(args.output)
        return 0

    if args.command == "load-neo4j":
        graph = load_dvm_xml(args.dvm_xml)
        load_graph_to_neo4j(graph, uri=args.uri, user=args.user, password=args.password, reset=args.reset)
        print(f"loaded {len(graph.edges)} edge(s)")
        return 0

    if args.command == "save-neo4j":
        graph = read_graph_from_neo4j(uri=args.uri, user=args.user, password=args.password)
        save_dvm_xml(graph, args.output)
        print(args.output)
        return 0

    if args.command == "delete-neo4j":
        delete_graph_from_neo4j(uri=args.uri, user=args.user, password=args.password)
        print("deleted")
        return 0

    if args.command == "export-json":
        graph = load_dvm_xml(args.dvm_xml)
        registry = DataSourceRegistry.from_xml(args.datasources_xml)
        plan = graph.to_query_plan(args.root, selected_only=not args.all_edges, bfs=True)
        result = QueryEvaluator(graph, registry).evaluate(plan, keys_mode=args.keys_mode)
        if args.output:
            result.write_json(args.output)
            print(args.output)
        else:
            print(json.dumps(result.to_json_records(), indent=2))
        return 0

    if args.command == "serve":
        from .server import serve
        serve(
            args.datasources_xml,
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=args.neo4j_password,
            host=args.host,
            port=args.port,
        )
        return 0

    if args.command == "list-datasources":
        datasources = load_datasources_xml(args.datasources_xml)
        for ds in datasources.values():
            desc = ds.get("filename") or ds.get("connection") or ds.get("system") or ""
            print(f"{ds.name}  [{ds.type}]  {desc}".rstrip())
        return 0

    if args.command == "add-datasource":
        options: dict[str, str] = {}
        for pair in args.options:
            if "=" not in pair:
                print(f"error: option must be KEY=VALUE, got: {pair!r}", flush=True)
                return 2
            k, _, v = pair.partition("=")
            options[k.strip()] = v.strip()
        datasource = DataSource(name=args.name, type=args.type, options=options)
        add_datasource_to_xml(args.datasources_xml, datasource)
        print(f"added {args.name!r}")
        return 0

    if args.command == "remove-datasource":
        removed = remove_datasource_from_xml(args.datasources_xml, args.name)
        if removed:
            print(f"removed {args.name!r}")
        else:
            print(f"not found: {args.name!r}")
            return 1
        return 0

    if args.command == "add-edge":
        graph = load_dvm_xml(args.dvm_xml)
        graph.create_edge(
            args.head,
            args.tail,
            args.datasource,
            head_description=args.head_description,
            tail_description=args.tail_description,
            query=args.query,
            key_positions=args.key,
            value_positions=args.value,
            selected=args.selected,
            bidirectional=args.bidirectional,
        )
        save_dvm_xml(graph, args.dvm_xml)
        print(f"added edge {args.head!r} -> {args.tail!r}")
        return 0

    if args.command == "remove-edge":
        count = remove_edge_from_dvm_xml(args.dvm_xml, args.head, args.tail)
        if count:
            print(f"removed {count} edge(s) {args.head!r} -> {args.tail!r}")
        else:
            print(f"no edges found: {args.head!r} -> {args.tail!r}")
            return 1
        return 0

    return 1


def _load_plan(path: str, query_format: str):
    if query_format == "xml":
        return load_query_xml(path)
    if query_format == "text":
        return load_query_text(path)
    suffixes = [suffix.lower() for suffix in Path(path).suffixes]
    if suffixes[-2:] == [".qdvm", ".xml"] or suffixes[-1:] == [".xml"]:
        return load_query_xml(path)
    return load_query_text(path)


if __name__ == "__main__":
    raise SystemExit(main())
