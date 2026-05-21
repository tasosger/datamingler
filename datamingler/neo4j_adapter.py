from __future__ import annotations

from .graph import DVMGraph
from .models import DVMEdge, positions_to_text


def load_graph_to_neo4j(
    graph: DVMGraph,
    *,
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "12345678",
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
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "12345678",
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
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "12345678",
) -> None:
    """Remove all DVM attribute nodes (and their relationships) from Neo4j."""
    driver = _driver(uri, user, password)
    try:
        with driver.session() as session:
            session.run("MATCH (n:attribute) DETACH DELETE n")
    finally:
        driver.close()


def _driver(uri: str, user: str, password: str):
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise RuntimeError("Neo4j support requires the optional dependency: pip install datamingler[neo4j]") from exc
    return GraphDatabase.driver(uri, auth=(user, password))
