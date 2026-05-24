from __future__ import annotations

from .graph import DVMGraph
from .models import DVMEdge, positions_to_text

# Default connection parameters — match the legacy Java defaults.
_DEFAULT_URI  = "bolt://localhost:7687"
_DEFAULT_USER = "neo4j"
_DEFAULT_PASS = "12345678"


# ── Bulk operations (used by CLI import/export commands) ───────────────────

def load_graph_to_neo4j(
    graph: DVMGraph,
    *,
    uri: str = _DEFAULT_URI,
    user: str = _DEFAULT_USER,
    password: str = _DEFAULT_PASS,
    reset: bool = False,
) -> None:
    """Persist a DVM graph to Neo4j using the legacy `attribute`/`has` schema."""
    driver = _driver(uri, user, password)
    try:
        with driver.session() as session:
            if reset:
                session.run("MATCH (n:attribute) DETACH DELETE n")
            for edge in graph.edges:
                session.run(
                    """
                    MERGE (a:attribute {name: $head_name})
                    SET a.description = $head_description
                    MERGE (b:attribute {name: $tail_name})
                    SET b.description = $tail_description
                    CREATE (a)-[:has {
                      datasource: $datasource,
                      query: $query,
                      key: $key,
                      value: $value,
                      selected: $selected,
                      description: $description
                    }]->(b)
                    """,
                    head_name=edge.head_name,
                    head_description=edge.head.description,
                    tail_name=edge.tail_name,
                    tail_description=edge.tail.description,
                    datasource=edge.datasource,
                    query=edge.query,
                    key=positions_to_text(edge.key_positions),
                    value=positions_to_text(edge.value_positions),
                    selected="true" if edge.selected else "false",
                    description=edge.description,
                )
            session.run(
                """
                MATCH (n:attribute)-[:has]->(m)
                WITH n, count(m) AS cnt
                WHERE cnt > 1
                SET n:primary
                """
            )
    finally:
        driver.close()


def read_graph_from_neo4j(
    *,
    uri: str = _DEFAULT_URI,
    user: str = _DEFAULT_USER,
    password: str = _DEFAULT_PASS,
) -> DVMGraph:
    """Read all Neo4j DVM `attribute` edges into an in-memory graph."""
    driver = _driver(uri, user, password)
    graph = DVMGraph()
    try:
        with driver.session() as session:
            records = session.run(
                """
                MATCH (n:attribute)-[r:has]->(m:attribute)
                RETURN n.name AS head_name,
                       n.description AS head_description,
                       m.name AS tail_name,
                       m.description AS tail_description,
                       r.datasource AS datasource,
                       r.query AS query,
                       r.key AS key,
                       r.value AS value,
                       r.selected AS selected,
                       r.description AS description
                """
            )
            for record in records:
                graph.add_edge(
                    DVMEdge.create(
                        record["head_name"],
                        record["tail_name"],
                        record["datasource"] or "",
                        head_description=record["head_description"] or "",
                        tail_description=record["tail_description"] or "",
                        query=record["query"] or "",
                        key_positions=record["key"] or "",
                        value_positions=record["value"] or "",
                        selected=str(record["selected"] or "").lower() == "true",
                        description=record["description"] or "",
                    )
                )
    finally:
        driver.close()
    return graph


def delete_graph_from_neo4j(
    *,
    uri: str = _DEFAULT_URI,
    user: str = _DEFAULT_USER,
    password: str = _DEFAULT_PASS,
) -> None:
    """Remove all DVM attribute nodes (and their relationships) from Neo4j."""
    driver = _driver(uri, user, password)
    try:
        with driver.session() as session:
            session.run("MATCH (n:attribute) DETACH DELETE n")
    finally:
        driver.close()


# ── Single-edge CRUD (used by the HTTP server) ─────────────────────────────

def add_edge_to_neo4j(
    edge: DVMEdge,
    *,
    uri: str = _DEFAULT_URI,
    user: str = _DEFAULT_USER,
    password: str = _DEFAULT_PASS,
) -> None:
    """Add a single DVM edge (and its nodes if they don't exist) to Neo4j."""
    driver = _driver(uri, user, password)
    try:
        with driver.session() as session:
            session.run(
                """
                MERGE (a:attribute {name: $head_name})
                SET a.description = $head_description
                MERGE (b:attribute {name: $tail_name})
                SET b.description = $tail_description
                CREATE (a)-[:has {
                  datasource: $datasource,
                  query: $query,
                  key: $key,
                  value: $value,
                  selected: $selected,
                  description: $description
                }]->(b)
                """,
                head_name=edge.head_name,
                head_description=edge.head.description,
                tail_name=edge.tail_name,
                tail_description=edge.tail.description,
                datasource=edge.datasource,
                query=edge.query,
                key=positions_to_text(edge.key_positions),
                value=positions_to_text(edge.value_positions),
                selected="true" if edge.selected else "false",
                description=edge.description,
            )
    finally:
        driver.close()


def update_edge_in_neo4j(
    head: str,
    tail: str,
    updates: dict,
    *,
    uri: str = _DEFAULT_URI,
    user: str = _DEFAULT_USER,
    password: str = _DEFAULT_PASS,
) -> None:
    """Update properties on all :has edges from *head* to *tail*.

    Accepted keys: ``selected`` (bool), ``datasource``, ``query``, ``description``.
    ``selected`` is stored as the string "true"/"false" to match the legacy layout.
    """
    props = dict(updates)
    if "selected" in props:
        props["selected"] = "true" if props["selected"] else "false"

    driver = _driver(uri, user, password)
    try:
        with driver.session() as session:
            session.run(
                """
                MATCH (a:attribute {name: $head})-[r:has]->(b:attribute {name: $tail})
                SET r += $props
                """,
                head=head.strip(),
                tail=tail.strip(),
                props=props,
            )
    finally:
        driver.close()


def remove_edge_from_neo4j(
    head: str,
    tail: str,
    *,
    uri: str = _DEFAULT_URI,
    user: str = _DEFAULT_USER,
    password: str = _DEFAULT_PASS,
) -> int:
    """Delete all :has edges from *head* to *tail*.  Returns the number removed."""
    driver = _driver(uri, user, password)
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (a:attribute {name: $head})-[r:has]->(b:attribute {name: $tail})
                WITH collect(r) AS rels
                FOREACH (r IN rels | DELETE r)
                RETURN size(rels) AS removed
                """,
                head=head.strip(),
                tail=tail.strip(),
            )
            record = result.single()
            return int(record["removed"]) if record else 0
    finally:
        driver.close()


# ── Internal helper ────────────────────────────────────────────────────────

def _driver(uri: str, user: str, password: str):
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise RuntimeError(
            "Neo4j support requires the optional dependency:\n"
            "  pip install datamingler[neo4j]"
        ) from exc
    return GraphDatabase.driver(uri, auth=(user, password))
