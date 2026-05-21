from __future__ import annotations

from collections import defaultdict

from .models import KeysMode


class KeyListStore:
    """In-memory equivalent of the legacy Redis key-list layout."""

    def __init__(self) -> None:
        self.clear()

    def clear(self) -> None:
        self._edge_keys: dict[tuple[str, str], set[str]] = defaultdict(set)
        self._values: dict[tuple[str, str, str], list[str]] = defaultdict(list)

    def add_value(self, root: str, child: str, key: str, value: str) -> None:
        root = root.strip()
        child = child.strip()
        key = str(key)
        self._edge_keys[(root, child)].add(key)
        self._values[(root, child, key)].append(str(value))

    def add_key(self, root: str, child: str, key: str) -> None:
        self._edge_keys[(root.strip(), child.strip())].add(str(key))

    def set_values(self, root: str, child: str, key: str, values: list[str]) -> None:
        root = root.strip()
        child = child.strip()
        key = str(key)
        if values:
            self._edge_keys[(root, child)].add(key)
            self._values[(root, child, key)] = [str(value) for value in values]
        else:
            self.remove_key(root, child, key)

    def get_values(self, root: str, child: str, key: str) -> list[str]:
        return list(self._values.get((root.strip(), child.strip(), str(key)), []))

    def edge_keys(self, root: str, child: str) -> set[str]:
        return set(self._edge_keys.get((root.strip(), child.strip()), set()))

    def has_edge(self, root: str, child: str) -> bool:
        return bool(self._edge_keys.get((root.strip(), child.strip())))

    def remove_key(self, root: str, child: str, key: str) -> None:
        root = root.strip()
        child = child.strip()
        key = str(key)
        self._edge_keys[(root, child)].discard(key)
        self._values.pop((root, child, key), None)

    def remove_edge(self, root: str, child: str) -> None:
        root = root.strip()
        child = child.strip()
        for key in list(self._edge_keys.get((root, child), set())):
            self._values.pop((root, child, key), None)
        self._edge_keys.pop((root, child), None)

    def combine_keys(self, root: str, children: list[str] | tuple[str, ...], mode: KeysMode) -> set[str]:
        if mode not in {"all", "intersect"}:
            raise ValueError("keys mode must be 'all' or 'intersect'")
        result: set[str] | None = None
        for child in children:
            keys = self.edge_keys(root, child)
            if result is None:
                result = keys
            elif mode == "all":
                result |= keys
            else:
                result &= keys
        return result or set()
