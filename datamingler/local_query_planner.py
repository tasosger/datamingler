from __future__ import annotations

import re
from collections import Counter, deque
from dataclasses import dataclass

from .graph import DVMGraph
from .models import QueryNode, QueryPlan
from .models import transformations_to_text


@dataclass(frozen=True)
class PlannedQuery:
    title: str
    query: str
    confidence: float
    notes: str = ""


def plan_natural_language(prompt: str, graph: DVMGraph, *, max_queries: int = 3) -> list[PlannedQuery]:
    """Translate a user request into one or more QDVM query candidates.

    This is intentionally deterministic. It provides the local pipeline that a
    hosted LLM can replace later: schema extraction, intent splitting, query
    planning, QDVM rendering, and validation.
    """
    intents = _split_intents(prompt)
    if not intents:
        return []
    queries = []
    for index, intent in enumerate(intents[:max_queries], start=1):
        query = _plan_intent(intent, graph, index)
        if query:
            queries.append(query)
    return queries


def _split_intents(prompt: str) -> list[str]:
    cleaned = " ".join(prompt.split())
    if not cleaned:
        return []
    parts = re.split(r"\s*(?:;|\n+|\balso\b|\bthen\b)\s*", cleaned, flags=re.IGNORECASE)
    return [part.strip(" .,") for part in parts if part.strip(" .,")]


def _plan_intent(intent: str, graph: DVMGraph, index: int) -> PlannedQuery | None:
    if not graph.edges:
        return None

    root = _choose_root(intent, graph)
    paths = _choose_output_paths(intent, graph, root)
    if not paths:
        paths = [[root, child] for child in graph.children(root, selected_only=True)[:4]]
    if not paths:
        paths = [[root, edge.tail_name] for edge in graph.edges if edge.head_name == root][:4]
    if not paths:
        return None

    plan = _build_plan(intent, graph, root, paths)
    query_text = _render_query(plan)
    title = _query_title(intent, index)
    confidence = 0.8 if _mentioned_nodes(intent, graph) else 0.45
    notes = "Generated from matching DVM node names and simple filter/aggregate cues."
    return PlannedQuery(title=title, query=query_text, confidence=confidence, notes=notes)


def _choose_root(intent: str, graph: DVMGraph) -> str:
    mentioned = _mentioned_nodes(intent, graph)
    heads = Counter(edge.head_name for edge in graph.edges if edge.selected)
    if not heads:
        heads = Counter(edge.head_name for edge in graph.edges)

    for name in mentioned:
        if name in heads:
            return name

    if heads:
        return heads.most_common(1)[0][0]
    return graph.edges[0].head_name


def _choose_output_paths(intent: str, graph: DVMGraph, root: str) -> list[list[str]]:
    mentioned = [name for name in _mentioned_nodes(intent, graph) if name != root]
    paths = []
    for node in mentioned:
        path = _find_path(graph, root, node)
        if path and len(path) > 1:
            paths.append(path)
    return _dedupe_paths(paths)


def _mentioned_nodes(intent: str, graph: DVMGraph) -> list[str]:
    text = intent.lower()
    matches = []
    for name in graph.nodes:
        if _node_matches_text(name, text) and name not in matches:
            matches.append(name)
    return matches


def _node_matches_text(name: str, text: str) -> bool:
    lowered = name.lower()
    variants = {
        lowered,
        lowered.replace("_", " "),
        lowered.replace("-", " "),
    }
    camel_words = re.sub(r"(?<!^)(?=[A-Z])", " ", name).lower()
    variants.add(camel_words)
    return any(re.search(rf"\b{re.escape(variant)}s?\b", text) for variant in variants if variant)


def _find_path(graph: DVMGraph, root: str, target: str) -> list[str] | None:
    queue: deque[list[str]] = deque([[root]])
    visited = {root}
    while queue:
        path = queue.popleft()
        current = path[-1]
        for child in graph.children(current, selected_only=True) or graph.children(current):
            if child in visited:
                continue
            next_path = [*path, child]
            if child == target:
                return next_path
            visited.add(child)
            queue.append(next_path)
    return None


def _dedupe_paths(paths: list[list[str]]) -> list[list[str]]:
    seen = set()
    result = []
    for path in paths:
        key = tuple(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def _build_plan(intent: str, graph: DVMGraph, root: str, paths: list[list[str]]) -> QueryPlan:
    labeler = _Labeler()
    root_label = labeler.label(root)
    draft: dict[str, dict[str, object]] = {
        root_label: {
            "label": root_label,
            "onnode": root,
            "children": [],
            "transformations": "",
            "theta": "",
            "output": False,
        }
    }

    for path in paths:
        parent_label = root_label
        for node in path[1:]:
            label = labeler.label(node)
            condition = _condition_for_node(intent, node, label)
            if label not in draft:
                draft[label] = {
                    "label": label,
                    "onnode": node,
                    "children": [],
                    "transformations": _transform_for_node(intent, node, labeler.label(node)),
                    "theta": "",
                    "output": False,
                }
            children = draft[parent_label]["children"]
            assert isinstance(children, list)
            if label not in children:
                children.append(label)
            if condition:
                existing_theta = str(draft[parent_label]["theta"] or "")
                draft[parent_label]["theta"] = f"({existing_theta}) and ({condition})" if existing_theta else condition
            parent_label = label
        draft[parent_label]["output"] = True

    nodes = {
        label: QueryNode.create(
            str(item["label"]),
            str(item["onnode"]),
            children=tuple(item["children"]),
            transformations=str(item["transformations"]),
            theta=str(item["theta"]),
            output=bool(item["output"]),
        )
        for label, item in draft.items()
    }
    return QueryPlan(root=root_label, nodes=nodes, order=tuple(draft))


def _transform_for_node(intent: str, node: str, label: str) -> str:
    text = intent.lower()
    if _wants_length(text, node):
        return f"map:python,,len(${label}$);aggregate:sum"
    if re.search(r"\b(count|number of|how many)\b", text):
        return "aggregate:count"
    if re.search(r"\b(sum|total)\b", text):
        return "aggregate:sum"
    if re.search(r"\b(avg|average|mean)\b", text):
        return "aggregate:average"
    if re.search(r"\b(min|minimum|smallest)\b", text):
        return "aggregate:min"
    if re.search(r"\b(max|maximum|largest|highest)\b", text):
        return "aggregate:max"
    return "aggregate:any"


def _condition_for_node(intent: str, node: str, label: str) -> str:
    text = intent.lower()
    if not _node_matches_text(node, text):
        return ""

    numeric = re.search(
        rf"{re.escape(node.lower())}\D+(?:over|above|greater than|>=|at least)\s+(-?\d+(?:\.\d+)?)",
        text,
    )
    if numeric:
        return f"float(${label}$) >= {numeric.group(1)}"

    numeric = re.search(
        rf"{re.escape(node.lower())}\D+(?:under|below|less than|<=|at most)\s+(-?\d+(?:\.\d+)?)",
        text,
    )
    if numeric:
        return f"float(${label}$) <= {numeric.group(1)}"

    year = re.search(rf"{re.escape(node.lower())}\D+(?:after|since)\s+(\d{{4}})", text)
    if year:
        return f"str(${label}$) >= '{year.group(1)}'"

    year = re.search(rf"{re.escape(node.lower())}\D+before\s+(\d{{4}})", text)
    if year:
        return f"str(${label}$) < '{year.group(1)}'"

    return ""


def _wants_length(text: str, node: str) -> bool:
    variants = [node.lower(), node.lower().replace("_", " "), node.lower().replace("-", " ")]
    for variant in variants:
        if not variant:
            continue
        if re.search(rf"\b{re.escape(variant)}\b\W+(?:\w+\W+){{0,2}}length\b", text):
            return True
        if re.search(rf"\blength\b\W+(?:\w+\W+){{0,2}}\b{re.escape(variant)}\b", text):
            return True
    return False


def _render_query(plan: QueryPlan) -> str:
    lines = []
    for label in plan.order:
        node = plan.nodes[label]
        lines.append(f"define {node.label} on {node.onnode}:")
        for child_label in node.children:
            child = plan.nodes[child_label]
            transform = transformations_to_text(child.transformations)
            lines.append(f"  compute {child.label} on {child.onnode} transformedby '{transform}'")
        output = [child for child in node.children if plan.nodes[child].output]
        if output:
            lines.append(f"  output {','.join(output)}")
        lines.append(f"  where {node.theta or 'True'}")
    return "\n".join(lines)


def _query_title(intent: str, index: int) -> str:
    words = re.findall(r"[A-Za-z0-9_]+", intent)
    if not words:
        return f"Generated {index}"
    return " ".join(words[:5]).title()


class _Labeler:
    def __init__(self) -> None:
        self._labels: dict[str, str] = {}
        self._used: set[str] = set()

    def label(self, node: str) -> str:
        if node not in self._labels:
            base = self.static_label(node)
            label = base
            suffix = 2
            while label in self._used:
                label = f"{base}{suffix}"
                suffix += 1
            self._labels[node] = label
            self._used.add(label)
        return self._labels[node]

    @staticmethod
    def static_label(node: str) -> str:
        parts = re.findall(r"[A-Za-z0-9]+", node)
        if not parts:
            return "N"
        if len(parts) == 1:
            label = "".join(char for char in parts[0] if char.isupper()) or parts[0][:3].title()
        else:
            label = "".join(part[0].upper() for part in parts if part)
        if not label[0].isalpha():
            label = f"N{label}"
        return label[:8]
