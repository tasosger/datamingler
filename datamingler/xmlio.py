from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .graph import DVMGraph
from .models import (
    DataSource,
    DVMEdge,
    QueryNode,
    QueryPlan,
    parse_transformations,
    positions_to_text,
    transformations_to_text,
)


def _text(element: ET.Element | None, default: str = "") -> str:
    if element is None or element.text is None:
        return default
    return element.text.strip()


def _bool_text(value: str) -> bool:
    return value.strip().lower() in {"true", "yes", "1"}


def load_dvm_xml(path: str | Path) -> DVMGraph:
    root = ET.parse(path).getroot()
    if root.tag != "edges":
        raise ValueError(f"Expected <edges> root in {path}")
    graph = DVMGraph()
    for edge_element in root.findall("edge"):
        head = edge_element.find("headnode")
        tail = edge_element.find("tailnode")
        edge = DVMEdge.create(
            _text(head.find("name") if head is not None else None),
            _text(tail.find("name") if tail is not None else None),
            _text(edge_element.find("datasource")),
            head_description=_text(head.find("description") if head is not None else None),
            tail_description=_text(tail.find("description") if tail is not None else None),
            query=_text(edge_element.find("query")),
            key_positions=_text(edge_element.find("key")),
            value_positions=_text(edge_element.find("value")),
            selected=_bool_text(_text(edge_element.find("selected"))),
            description=_text(edge_element.find("description")),
        )
        graph.add_edge(edge)
    return graph


def save_dvm_xml(graph: DVMGraph, path: str | Path) -> None:
    root = ET.Element("edges")
    for edge in graph.edges:
        edge_element = ET.SubElement(root, "edge")
        head = ET.SubElement(edge_element, "headnode")
        ET.SubElement(head, "name").text = edge.head_name
        ET.SubElement(head, "description").text = edge.head.description
        tail = ET.SubElement(edge_element, "tailnode")
        ET.SubElement(tail, "name").text = edge.tail_name
        ET.SubElement(tail, "description").text = edge.tail.description
        ET.SubElement(edge_element, "datasource").text = edge.datasource
        ET.SubElement(edge_element, "query").text = edge.query
        if edge.description:
            ET.SubElement(edge_element, "description").text = edge.description
        ET.SubElement(edge_element, "selected").text = "true" if edge.selected else "false"
        ET.SubElement(edge_element, "key").text = positions_to_text(edge.key_positions)
        ET.SubElement(edge_element, "value").text = positions_to_text(edge.value_positions)
    _write_xml(root, path)


def load_datasources_xml(path: str | Path) -> dict[str, DataSource]:
    root = ET.parse(path).getroot()
    if root.tag != "datasources":
        raise ValueError(f"Expected <datasources> root in {path}")
    datasources: dict[str, DataSource] = {}
    for element in root.findall("datasource"):
        options = {child.tag: _text(child) for child in element if child.tag != "name"}
        datasource = DataSource(
            name=_text(element.find("name")),
            type=element.attrib.get("type", ""),
            options=options,
        )
        datasources[datasource.name] = datasource
    return datasources


def save_datasources_xml(datasources: dict[str, DataSource], path: str | Path) -> None:
    root = ET.Element("datasources")
    for datasource in datasources.values():
        element = ET.SubElement(root, "datasource", {"type": datasource.type})
        ET.SubElement(element, "name").text = datasource.name
        for key, value in datasource.options.items():
            ET.SubElement(element, key).text = value
    _write_xml(root, path)


def load_query_xml(path: str | Path) -> QueryPlan:
    root = ET.parse(path).getroot()
    if root.tag != "query":
        raise ValueError(f"Expected <query> root in {path}")
    nodes: dict[str, QueryNode] = {}
    order: list[str] = []
    for node_element in root.findall("node"):
        node = QueryNode.create(
            _text(node_element.find("label")),
            _text(node_element.find("onnode")),
            children=_text(node_element.find("children")),
            transformations=_text(node_element.find("transformations")),
            theta=_text(node_element.find("theta")),
            output=_text(node_element.find("output")).lower() == "yes",
        )
        nodes[node.label] = node
        order.append(node.label)
    return QueryPlan(root=_text(root.find("rootnode")), nodes=nodes, order=tuple(order))


def save_query_xml(plan: QueryPlan, path: str | Path) -> None:
    root = ET.Element("query")
    ET.SubElement(root, "rootnode").text = plan.root
    for label in plan.order:
        node = plan.nodes[label]
        element = ET.SubElement(root, "node")
        ET.SubElement(element, "label").text = node.label
        ET.SubElement(element, "onnode").text = node.onnode
        ET.SubElement(element, "children").text = ",".join(node.children)
        ET.SubElement(element, "transformations").text = transformations_to_text(node.transformations)
        ET.SubElement(element, "theta").text = node.theta
        ET.SubElement(element, "output").text = "yes" if node.output else "no"
    _write_xml(root, path)


_DEFINE_RE = re.compile(r"^define\s+(?P<label>\S+)\s+on\s+(?P<onnode>[^:]+):\s*$", re.IGNORECASE)
_USING_RE = re.compile(r"^using\s+(?P<onnode>.+?)\s+as\s+(?P<label>\S+):\s*$", re.IGNORECASE)
_COMPUTE_RE = re.compile(
    r"^compute\s+(?P<label>\S+)\s+on\s+(?P<onnode>\S+)(?:\s+transformed\s*by|\s+transformedby)\s+(?P<transforms>.*)$",
    re.IGNORECASE,
)


def parse_query_text(text: str) -> QueryPlan:
    root_label = ""
    order: list[str] = []
    nodes: dict[str, QueryNode] = {}
    draft: dict[str, dict[str, object]] = {}
    current_label = ""

    def ensure_node(label: str, onnode: str = "") -> dict[str, object]:
        label = label.strip()
        if label not in draft:
            draft[label] = {
                "label": label,
                "onnode": onnode.strip(),
                "children": [],
                "transformations": "",
                "theta": "",
                "output": False,
            }
            order.append(label)
        elif onnode.strip():
            draft[label]["onnode"] = onnode.strip()
        return draft[label]

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        define = _DEFINE_RE.match(line) or _USING_RE.match(line)
        if define:
            label = define.group("label").strip()
            onnode = define.group("onnode").strip()
            ensure_node(label, onnode)
            current_label = label
            if not root_label:
                root_label = label
            continue

        compute = _COMPUTE_RE.match(line)
        if compute:
            if not current_label:
                raise ValueError(f"compute clause has no active define/using clause: {line}")
            label = compute.group("label").strip()
            onnode = compute.group("onnode").strip()
            transforms = _strip_outer_quotes(compute.group("transforms").strip())
            ensure_node(label, onnode)["transformations"] = transforms
            children = draft[current_label]["children"]
            assert isinstance(children, list)
            children.append(label)
            continue

        if line.lower().startswith("output"):
            labels = line[len("output") :].strip()
            for label in [part.strip() for part in labels.split(",") if part.strip()]:
                ensure_node(label)["output"] = True
            continue

        if line.lower().startswith("where"):
            if not current_label:
                raise ValueError(f"where clause has no active define/using clause: {line}")
            draft[current_label]["theta"] = line[len("where") :].strip()
            continue

        raise ValueError(f"Could not parse query line: {line}")

    if not root_label:
        raise ValueError("Query text does not define a root node")

    query_nodes: dict[str, QueryNode] = {}
    for label in order:
        item = draft[label]
        query_nodes[label] = QueryNode.create(
            str(item["label"]),
            str(item["onnode"] or item["label"]),
            children=tuple(item["children"]),
            transformations=str(item["transformations"]),
            theta=str(item["theta"]),
            output=bool(item["output"]),
        )
    return QueryPlan(root=root_label, nodes=query_nodes, order=tuple(order))


def load_query_text(path: str | Path) -> QueryPlan:
    return parse_query_text(Path(path).read_text(encoding="utf-8"))


def add_datasource_to_xml(path: str | Path, datasource: DataSource) -> None:
    """Append *datasource* to an existing datasources XML file.

    Mirrors the operation performed by ``createSource.php`` in the original web UI.
    Raises ``ValueError`` if a datasource with the same name already exists.
    """
    path = Path(path)
    root = ET.parse(path).getroot()
    for element in root.findall("datasource"):
        if _text(element.find("name")) == datasource.name:
            raise ValueError(f"Datasource {datasource.name!r} already exists in {path}")
    element = ET.SubElement(root, "datasource", {"type": datasource.type})
    ET.SubElement(element, "name").text = datasource.name
    for key, value in datasource.options.items():
        ET.SubElement(element, key).text = value
    _write_xml(root, path)


def remove_datasource_from_xml(path: str | Path, name: str) -> bool:
    """Remove the datasource named *name* from the XML file.

    Returns ``True`` if the datasource was found and removed, ``False`` otherwise.
    Mirrors the operation performed by ``deleteSource.php`` in the original web UI.
    """
    path = Path(path)
    root = ET.parse(path).getroot()
    removed = False
    for element in root.findall("datasource"):
        if _text(element.find("name")) == name.strip():
            root.remove(element)
            removed = True
            break
    if removed:
        _write_xml(root, path)
    return removed


def add_edge_to_dvm_xml(path: str | Path, edge: DVMEdge) -> None:
    """Append *edge* to an existing DVM XML file.

    Mirrors the Neo4j edge-creation performed by ``createEdgeNeo4j.java`` /
    ``createCSVEdgesNeo4j.java``, but targets the XML representation instead.
    """
    path = Path(path)
    root = ET.parse(path).getroot()
    edge_element = ET.SubElement(root, "edge")
    head = ET.SubElement(edge_element, "headnode")
    ET.SubElement(head, "name").text = edge.head_name
    ET.SubElement(head, "description").text = edge.head.description
    tail = ET.SubElement(edge_element, "tailnode")
    ET.SubElement(tail, "name").text = edge.tail_name
    ET.SubElement(tail, "description").text = edge.tail.description
    ET.SubElement(edge_element, "datasource").text = edge.datasource
    ET.SubElement(edge_element, "query").text = edge.query
    if edge.description:
        ET.SubElement(edge_element, "description").text = edge.description
    ET.SubElement(edge_element, "selected").text = "true" if edge.selected else "false"
    ET.SubElement(edge_element, "key").text = positions_to_text(edge.key_positions)
    ET.SubElement(edge_element, "value").text = positions_to_text(edge.value_positions)
    _write_xml(root, path)


def remove_edge_from_dvm_xml(path: str | Path, head_name: str, tail_name: str) -> int:
    """Remove all DVM edges from *head_name* to *tail_name* in the XML file.

    Returns the number of edges removed.
    """
    path = Path(path)
    root = ET.parse(path).getroot()
    to_remove = []
    for edge_element in root.findall("edge"):
        head = edge_element.find("headnode")
        tail = edge_element.find("tailnode")
        h = _text(head.find("name") if head is not None else None)
        t = _text(tail.find("name") if tail is not None else None)
        if h == head_name.strip() and t == tail_name.strip():
            to_remove.append(edge_element)
    for element in to_remove:
        root.remove(element)
    if to_remove:
        _write_xml(root, path)
    return len(to_remove)


def _strip_outer_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _write_xml(root: ET.Element, path: str | Path) -> None:
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
