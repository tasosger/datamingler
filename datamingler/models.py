from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

KeysMode = Literal["all", "intersect"]


def normalize_name(value: str | None) -> str:
    return (value or "").strip()


def parse_positions(value: str | int | tuple[int, ...] | list[int]) -> tuple[int, ...]:
    if isinstance(value, int):
        return (value,)
    if isinstance(value, (tuple, list)):
        return tuple(int(part) for part in value)
    text = normalize_name(value)
    if not text:
        return ()
    return tuple(int(part.strip()) for part in text.split(",") if part.strip())


def positions_to_text(positions: tuple[int, ...]) -> str:
    return ",".join(str(position) for position in positions)


@dataclass(frozen=True)
class AttributeNode:
    name: str
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", normalize_name(self.name))
        object.__setattr__(self, "description", normalize_name(self.description))


@dataclass(frozen=True)
class DVMEdge:
    head: AttributeNode
    tail: AttributeNode
    datasource: str
    query: str = ""
    key_positions: tuple[int, ...] = field(default_factory=tuple)
    value_positions: tuple[int, ...] = field(default_factory=tuple)
    selected: bool = False
    description: str = ""

    @property
    def head_name(self) -> str:
        return self.head.name

    @property
    def tail_name(self) -> str:
        return self.tail.name

    @classmethod
    def create(
        cls,
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
        description: str = "",
    ) -> "DVMEdge":
        return cls(
            head=AttributeNode(head_name, head_description),
            tail=AttributeNode(tail_name, tail_description),
            datasource=normalize_name(datasource),
            query=query or "",
            key_positions=parse_positions(key_positions),
            value_positions=parse_positions(value_positions),
            selected=selected,
            description=description or "",
        )


@dataclass(frozen=True)
class DataSource:
    name: str
    type: str
    options: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", normalize_name(self.name))
        object.__setattr__(self, "type", normalize_name(self.type).lower())
        object.__setattr__(
            self,
            "options",
            {normalize_name(key): normalize_name(value) for key, value in self.options.items()},
        )

    def get(self, key: str, default: str = "") -> str:
        return self.options.get(key, default)


@dataclass(frozen=True)
class Transformation:
    name: str
    raw_parameters: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", normalize_name(self.name).lower())
        object.__setattr__(self, "raw_parameters", (self.raw_parameters or "").strip())


def parse_transformations(value: str | None) -> tuple[Transformation, ...]:
    text = (value or "").strip()
    if not text or text.lower() == "null":
        return ()
    transformations: list[Transformation] = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        name, separator, parameters = part.partition(":")
        if not separator:
            transformations.append(Transformation(name, ""))
        else:
            transformations.append(Transformation(name, parameters))
    return tuple(transformations)


def transformations_to_text(transformations: tuple[Transformation, ...]) -> str:
    parts = []
    for transformation in transformations:
        if transformation.raw_parameters:
            parts.append(f"{transformation.name}:{transformation.raw_parameters}")
        else:
            parts.append(transformation.name)
    return ";".join(parts)


@dataclass(frozen=True)
class QueryNode:
    label: str
    onnode: str
    children: tuple[str, ...] = field(default_factory=tuple)
    transformations: tuple[Transformation, ...] = field(default_factory=tuple)
    theta: str = ""
    output: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", normalize_name(self.label))
        object.__setattr__(self, "onnode", normalize_name(self.onnode))
        object.__setattr__(self, "children", tuple(normalize_name(child) for child in self.children if normalize_name(child)))
        object.__setattr__(self, "theta", (self.theta or "").strip())

    @classmethod
    def create(
        cls,
        label: str,
        onnode: str,
        *,
        children: str | list[str] | tuple[str, ...] = (),
        transformations: str | tuple[Transformation, ...] = (),
        theta: str = "",
        output: bool | str = False,
    ) -> "QueryNode":
        if isinstance(children, str):
            children_tuple = tuple(part.strip() for part in children.split(",") if part.strip())
        else:
            children_tuple = tuple(children)
        if isinstance(transformations, str):
            transformation_tuple = parse_transformations(transformations)
        else:
            transformation_tuple = transformations
        output_bool = output if isinstance(output, bool) else output.strip().lower() == "yes"
        return cls(
            label=label,
            onnode=onnode,
            children=children_tuple,
            transformations=transformation_tuple,
            theta=theta,
            output=output_bool,
        )


@dataclass(frozen=True)
class QueryPlan:
    root: str
    nodes: dict[str, QueryNode]
    order: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        root = normalize_name(self.root)
        object.__setattr__(self, "root", root)
        if root not in self.nodes:
            raise ValueError(f"Query root {root!r} is not defined as a node")
        if not self.order:
            object.__setattr__(self, "order", tuple(self.nodes))
        missing_children = [
            child
            for node in self.nodes.values()
            for child in node.children
            if child not in self.nodes
        ]
        if missing_children:
            missing = ", ".join(sorted(set(missing_children)))
            raise ValueError(f"Query references undefined child node(s): {missing}")
