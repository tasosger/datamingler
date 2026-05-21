from __future__ import annotations

import importlib
from typing import Any

from .kvstore import KeyListStore
from .models import KeysMode, Transformation


def apply_transformations(store: KeyListStore, root: str, child: str, transformations: tuple[Transformation, ...]) -> None:
    for transformation in transformations:
        if transformation.name == "aggregate":
            aggregate_edge(store, root, child, transformation.raw_parameters.strip().lower())
        elif transformation.name == "filter":
            filter_edge(store, root, child, transformation.raw_parameters)
        elif transformation.name == "map":
            map_edge(store, root, child, transformation.raw_parameters)
        else:
            raise NotImplementedError(f"Unsupported transformation: {transformation.name!r}")


def aggregate_edge(store: KeyListStore, root: str, child: str, aggregate_type: str) -> None:
    aggregate_type = {"avg": "average"}.get(aggregate_type, aggregate_type)
    for key in list(store.edge_keys(root, child)):
        values = store.get_values(root, child, key)
        if aggregate_type == "min":
            result = _min(values)
        elif aggregate_type == "max":
            result = _max(values)
        elif aggregate_type == "sum":
            result = _sum(values)
        elif aggregate_type == "average":
            result = _average(values)
        elif aggregate_type == "count":
            result = str(len(values))
        elif aggregate_type == "any":
            result = values[0] if values else None
        else:
            raise NotImplementedError(f"Unsupported aggregate type: {aggregate_type!r}")
        store.set_values(root, child, key, [] if result is None else [result])


def filter_edge(store: KeyListStore, root: str, child: str, expression: str) -> None:
    python_expression = _replace_placeholder(expression, child, "value")
    for key in list(store.edge_keys(root, child)):
        kept = [
            value
            for value in store.get_values(root, child, key)
            if bool(_safe_eval(python_expression, {"key": key, "value": value}))
        ]
        store.set_values(root, child, key, kept)


def map_edge(store: KeyListStore, root: str, child: str, parameters: str) -> None:
    host, package, expression = _split_map_parameters(parameters)
    if host and host.lower() != "python":
        raise NotImplementedError("Only python map transformations are supported")
    extra_globals: dict[str, Any] = {}
    if package:
        module = importlib.import_module(package)
        extra_globals[package.split(".")[-1]] = module
    python_expression = _replace_placeholder(expression, child, "value")
    for key in list(store.edge_keys(root, child)):
        mapped = [
            str(_safe_eval(python_expression, {"key": key, "value": value}, extra_globals))
            for value in store.get_values(root, child, key)
        ]
        store.set_values(root, child, key, mapped)


def theta_select(
    store: KeyListStore,
    root: str,
    new_child: str,
    all_children: tuple[str, ...],
    output_children: tuple[str, ...],
    theta: str,
    keys_mode: KeysMode,
) -> None:
    del keys_mode
    if not all_children:
        return

    keys: set[str] | None = None
    for child in all_children:
        child_keys = store.edge_keys(root, child)
        keys = child_keys if keys is None else keys & child_keys
    if keys is None:
        return

    store.remove_edge(root, new_child)
    for key in keys:
        values_by_child = {child: store.get_values(root, child, key) for child in all_children}
        if _theta_matches(theta, root, key, values_by_child):
            store.add_key(root, new_child, key)
            if output_children:
                for child in output_children:
                    for value in values_by_child.get(child, []):
                        store.add_value(root, new_child, key, value)
            else:
                store.add_value(root, new_child, key, key)


def roll_up_edge(store: KeyListStore, root: str, child: str, child_child: str) -> None:
    """Replace each value-list in root→child with values those values have in child→child_child.

    For every key in root→child the current list of values (which are keys into
    child→child_child) is replaced by the union of their corresponding child_child
    value-lists.  This mirrors rollUpOp.java and is the join step of the original
    Java evalQuery evaluation pipeline.
    """
    for key in list(store.edge_keys(root, child)):
        values = store.get_values(root, child, key)
        new_values: list[str] = []
        for value in values:
            new_values.extend(store.get_values(child, child_child, value))
        store.set_values(root, child, key, new_values)


def constrain_parent_edge(store: KeyListStore, parent: str, child: str, valid_values: set[str]) -> None:
    for key in list(store.edge_keys(parent, child)):
        kept = [value for value in store.get_values(parent, child, key) if value in valid_values]
        store.set_values(parent, child, key, kept)


def _theta_matches(theta: str, root: str, key: str, values_by_child: dict[str, list[str]]) -> bool:
    expression = (theta or "").strip()
    if not expression:
        return True
    expression = _replace_placeholder(expression, root, "key")
    variables: dict[str, Any] = {"key": key}
    for child, values in values_by_child.items():
        variable = _variable_name(child)
        variables[variable] = values[0] if values else ""
        expression = _replace_placeholder(expression, child, variable)
    return bool(_safe_eval(expression, variables))


def _safe_eval(expression: str, variables: dict[str, Any], extra_globals: dict[str, Any] | None = None) -> Any:
    safe_builtins = {
        "abs": abs,
        "bool": bool,
        "float": float,
        "int": int,
        "len": len,
        "max": max,
        "min": min,
        "round": round,
        "str": str,
        "sum": sum,
    }
    globals_dict = {"__builtins__": safe_builtins}
    if extra_globals:
        globals_dict.update(extra_globals)
    return eval(expression, globals_dict, variables)


def _replace_placeholder(expression: str, label: str, replacement: str) -> str:
    return expression.replace(f"${label}$", replacement)


def _variable_name(label: str) -> str:
    result = []
    for index, char in enumerate(label):
        if char.isalnum() or char == "_":
            result.append(char)
        else:
            result.append("_")
    name = "".join(result) or "value"
    if name[0].isdigit():
        name = f"v_{name}"
    return name


def _split_map_parameters(parameters: str) -> tuple[str, str, str]:
    parts = parameters.split(",", 2)
    if len(parts) == 1:
        return "python", "", parts[0]
    if len(parts) == 2:
        return parts[0], "", parts[1]
    return parts[0], parts[1], parts[2]


def _is_numeric(value: str) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _numeric_values(values: list[str]) -> list[float]:
    return [float(value) for value in values if _is_numeric(value)]


def _min(values: list[str]) -> str | None:
    if not values:
        return None
    if all(_is_numeric(value) for value in values):
        return str(min(float(value) for value in values))
    return min(values)


def _max(values: list[str]) -> str | None:
    if not values:
        return None
    if all(_is_numeric(value) for value in values):
        return str(max(float(value) for value in values))
    return max(values)


def _sum(values: list[str]) -> str | None:
    numbers = _numeric_values(values)
    return str(sum(numbers)) if numbers else None


def _average(values: list[str]) -> str | None:
    numbers = _numeric_values(values)
    return str(sum(numbers) / len(numbers)) if numbers else None
