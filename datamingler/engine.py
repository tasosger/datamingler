from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .graph import DVMGraph
from .kvstore import KeyListStore
from .models import KeysMode, QueryPlan
from .operators import apply_transformations, constrain_parent_edge, theta_select
from .sources import DataSourceRegistry, EdgeMaterializer


@dataclass
class EvaluationResult:
    plan: QueryPlan
    store: KeyListStore
    keys: list[str]

    def to_json_records(self) -> list[dict[str, Any]]:
        root = self.plan.nodes[self.plan.root]
        output_children = [child for child in root.children if self.plan.nodes[child].output]
        records: list[dict[str, Any]] = []
        for key in self.keys:
            record: dict[str, Any] = {self._field_name(root.label): key}
            for child in output_children:
                record.update(self._json_child(key, root.label, child))
            records.append(record)
        return records

    def to_rows(self) -> list[dict[str, str]]:
        root = self.plan.nodes[self.plan.root]
        output_children = [child for child in root.children if self.plan.nodes[child].output]
        rows: list[dict[str, str]] = []
        for key in self.keys:
            row = {self._field_name(root.label): key}
            for child in output_children:
                values = self.store.get_values(root.label, child, key)
                row[self._field_name(child)] = ",".join(values)
            rows.append(row)
        return rows

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_json_records(), indent=2), encoding="utf-8")

    def write_csv(self, path: str | Path) -> None:
        rows = self.to_rows()
        if not rows:
            Path(path).write_text("", encoding="utf-8")
            return
        with Path(path).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def _json_child(self, key: str, root_label: str, child_label: str) -> dict[str, Any]:
        child = self.plan.nodes[child_label]
        output_children = [item for item in child.children if self.plan.nodes[item].output]
        values = self.store.get_values(root_label, child_label, key)
        field_name = self._field_name(child_label)
        if not output_children:
            return {field_name: _json_value(values)}

        nested_items: list[dict[str, Any]] = []
        for value in values:
            item: dict[str, Any] = {field_name: value}
            for grandchild in output_children:
                item.update(self._json_child(value, child_label, grandchild))
            nested_items.append(item)
        return {f"{field_name}_s": nested_items}

    def _field_name(self, label: str) -> str:
        node = self.plan.nodes[label]
        return f"{node.onnode}-{node.label}"


class QueryEvaluator:
    def __init__(self, graph: DVMGraph, registry: DataSourceRegistry, *, store: KeyListStore | None = None) -> None:
        self.graph = graph
        self.registry = registry
        self.store = store or KeyListStore()
        self.materializer = EdgeMaterializer(registry)
        self.plan: QueryPlan | None = None
        self.keys_mode: KeysMode = "all"

    def evaluate(self, plan: QueryPlan, *, keys_mode: KeysMode = "all") -> EvaluationResult:
        if keys_mode not in {"all", "intersect"}:
            raise ValueError("keys_mode must be 'all' or 'intersect'")
        self.plan = plan
        self.keys_mode = keys_mode
        self.store.clear()

        root = plan.nodes[plan.root]
        self._materialize_tree(root.label)
        self._eval_child("top", root.label)

        output_children = [child for child in root.children if plan.nodes[child].output]
        keys = self.store.edge_keys("top", root.label)
        output_keys = self.store.combine_keys(root.label, output_children, keys_mode) if output_children else set()
        if output_keys:
            keys &= output_keys
        return EvaluationResult(plan=plan, store=self.store, keys=sorted(keys))

    def _materialize_tree(self, label: str) -> None:
        assert self.plan is not None
        node = self.plan.nodes[label]
        for child_label in node.children:
            child = self.plan.nodes[child_label]
            if not self.store.has_edge(label, child_label):
                self.materializer.materialize_pair(
                    self.graph,
                    node.onnode,
                    child.onnode,
                    self.store,
                    root_alias=label,
                    child_alias=child_label,
                )
            self._materialize_tree(child_label)

    def _eval_child(self, parent_label: str, label: str) -> None:
        assert self.plan is not None
        node = self.plan.nodes[label]
        if not node.children:
            return

        for child_label in node.children:
            child = self.plan.nodes[child_label]
            self._eval_child(label, child_label)
            apply_transformations(self.store, label, child_label, child.transformations)

        all_children = tuple(node.children)
        output_children = tuple(child for child in node.children if self.plan.nodes[child].output)
        synthetic_child = f"childOf{label}"
        theta_select(
            self.store,
            label,
            synthetic_child,
            all_children,
            output_children,
            node.theta,
            self.keys_mode,
        )
        valid_keys = self.store.edge_keys(label, synthetic_child)

        if parent_label == "top":
            self.store.remove_edge(parent_label, label)
            for key in valid_keys:
                self.store.add_key(parent_label, label, key)
        else:
            constrain_parent_edge(self.store, parent_label, label, valid_keys)


def _json_value(values: list[str]) -> Any:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return values
