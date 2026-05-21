from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import TYPE_CHECKING, Iterable

from .models import AttributeNode, DVMEdge

if TYPE_CHECKING:
    from .models import QueryPlan


class DVMGraph:
    """In-memory DVM graph preserving the legacy attribute/has-edge model."""

    def __init__(self, edges: Iterable[DVMEdge] | None = None) -> None:
        self.nodes: dict[str, AttributeNode] = {}
        self.edges: list[DVMEdge] = []
        self._edges_by_pair: dict[tuple[str, str], list[DVMEdge]] = defaultdict(list)
        if edges:
            for edge in edges:
                self.add_edge(edge)

    def add_edge(self, edge: DVMEdge) -> None:
        self.nodes[edge.head_name] = edge.head
        self.nodes[edge.tail_name] = edge.tail
        self.edges.append(edge)
        self._edges_by_pair[(edge.head_name, edge.tail_name)].append(edge)

    def create_edge(
        self,
        head_name: str,
        tail_name: str,
        datasource: str,
        *,
        head_description: str = "",
        tail_description: str = "",
        query: str = "",
        key_positions: str | int | tuple[int, ...] | list[int] = (),
        value_positions: str | int | tuple[int, ...] | list[int] = (),
        selected: bool = False,
        bidirectional: bool = False,
    ) -> None:
        edge = DVMEdge.create(
            head_name,
            tail_name,
            datasource,
            head_description=head_description,
            tail_description=tail_description,
            query=query,
            key_positions=key_positions,
            value_positions=value_positions,
            selected=selected,
        )
        self.add_edge(edge)
        if bidirectional:
            self.add_edge(
                DVMEdge.create(
                    tail_name,
                    head_name,
                    datasource,
                    head_description=tail_description,
                    tail_description=head_description,
                    query=query,
                    key_positions=value_positions,
                    value_positions=key_positions,
                    selected=selected,
                )
            )

    def edges_between(self, head_name: str, tail_name: str) -> list[DVMEdge]:
        return list(self._edges_by_pair.get((head_name.strip(), tail_name.strip()), []))

    def children(self, head_name: str, *, selected_only: bool = False) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for edge in self.edges:
            if edge.head_name != head_name.strip():
                continue
            if selected_only and not edge.selected:
                continue
            if edge.tail_name not in seen:
                seen.add(edge.tail_name)
                result.append(edge.tail_name)
        return result

    def selected_copy(self, selected_edges: Iterable[tuple[str, str]]) -> "DVMGraph":
        selected = set(selected_edges)
        copied = DVMGraph()
        for edge in self.edges:
            copied.add_edge(replace(edge, selected=(edge.head_name, edge.tail_name) in selected))
        return copied

    def require_edge(self, head_name: str, tail_name: str) -> list[DVMEdge]:
        edges = self.edges_between(head_name, tail_name)
        if not edges:
            raise KeyError(f"No DVM edge exists from {head_name!r} to {tail_name!r}")
        return edges

    def to_query_plan(self, root: str, *, selected_only: bool = True, bfs: bool = True) -> "QueryPlan":
        """Auto-generate a query plan by traversing DVM edges from *root*.

        Mirrors the ``createJSON`` / ``treeType=bfs`` behaviour from the original
        Java implementation: BFS from *root*, including only selected edges when
        *selected_only=True*, and avoiding cycles when *bfs=True*.
        """
        from .models import QueryNode, QueryPlan

        visited: set[str] = {root}
        queue: list[str] = [root]
        node_children: dict[str, list[str]] = {}

        while queue:
            current = queue.pop(0)
            child_names = self.children(current, selected_only=selected_only)
            children_for_node: list[str] = []
            for child in child_names:
                if bfs and child in visited:
                    continue
                visited.add(child)
                children_for_node.append(child)
                queue.append(child)
            node_children[current] = children_for_node

        nodes: dict[str, QueryNode] = {}
        order: list[str] = [root]
        for name in list(node_children):
            order.extend(c for c in node_children[name] if c not in order)

        for name in order:
            nodes[name] = QueryNode.create(
                label=name,
                onnode=name,
                children=tuple(node_children.get(name, [])),
                output=name != root,
            )

        return QueryPlan(root=root, nodes=nodes, order=tuple(order))
