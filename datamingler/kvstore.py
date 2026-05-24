from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from .models import KeysMode


class KeyListStore:
    """Redis-backed key-list store matching the Java Jedis layout.

    Key convention (mirrors loadEdges.java / evalQuery.java):
      - Edge set:   {root}-{child}         → Redis SET  (set of keys for this edge)
      - Value list: {root}-{child}:{key}   → Redis LIST (values for a given key)

    Connect to the same host/port as the Java app: 127.0.0.1:6379.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 6379) -> None:
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError(
                "Redis support requires: pip install datamingler[redis]"
            ) from exc
        self._redis = redis.Redis(host=host, port=port, decode_responses=True)

    def clear(self) -> None:
        self._redis.flushall()

    def add_value(self, root: str, child: str, key: str, value: str) -> None:
        root = root.strip()
        child = child.strip()
        key = str(key)
        edge = f"{root}-{child}"
        self._redis.rpush(f"{edge}:{key}", str(value))
        self._redis.sadd(edge, key)

    def add_key(self, root: str, child: str, key: str) -> None:
        root = root.strip()
        child = child.strip()
        self._redis.sadd(f"{root}-{child}", str(key))

    def set_values(self, root: str, child: str, key: str, values: list[str]) -> None:
        root = root.strip()
        child = child.strip()
        key = str(key)
        edge = f"{root}-{child}"
        pipe = self._redis.pipeline()
        pipe.delete(f"{edge}:{key}")
        if values:
            pipe.rpush(f"{edge}:{key}", *[str(v) for v in values])
            pipe.sadd(edge, key)
        else:
            pipe.srem(edge, key)
        pipe.execute()

    def get_values(self, root: str, child: str, key: str) -> list[str]:
        edge = f"{root.strip()}-{child.strip()}"
        return self._redis.lrange(f"{edge}:{str(key)}", 0, -1)

    def edge_keys(self, root: str, child: str) -> set[str]:
        edge = f"{root.strip()}-{child.strip()}"
        return self._redis.smembers(edge)

    def has_edge(self, root: str, child: str) -> bool:
        edge = f"{root.strip()}-{child.strip()}"
        return self._redis.scard(edge) > 0

    def remove_key(self, root: str, child: str, key: str) -> None:
        root = root.strip()
        child = child.strip()
        key = str(key)
        edge = f"{root}-{child}"
        pipe = self._redis.pipeline()
        pipe.delete(f"{edge}:{key}")
        pipe.srem(edge, key)
        pipe.execute()

    def remove_edge(self, root: str, child: str) -> None:
        root = root.strip()
        child = child.strip()
        edge = f"{root}-{child}"
        keys = self._redis.smembers(edge)
        pipe = self._redis.pipeline()
        for key in keys:
            pipe.delete(f"{edge}:{key}")
        pipe.delete(edge)
        pipe.execute()

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

    @contextmanager
    def pipeline(self) -> Generator[_PipelinedStore, None, None]:
        """Batch writes via a Redis pipeline — mirrors Java's Pipeline/sync pattern."""
        pipe = self._redis.pipeline()
        pstore = _PipelinedStore(pipe)
        yield pstore
        pipe.execute()


class _PipelinedStore:
    """Queues add_value / add_key calls on a Redis pipeline without per-call round-trips."""

    def __init__(self, pipe: object) -> None:
        self._pipe = pipe

    def add_value(self, root: str, child: str, key: str, value: str) -> None:
        root = root.strip()
        child = child.strip()
        key = str(key)
        edge = f"{root}-{child}"
        self._pipe.rpush(f"{edge}:{key}", str(value))
        self._pipe.sadd(edge, key)

    def add_key(self, root: str, child: str, key: str) -> None:
        root = root.strip()
        child = child.strip()
        self._pipe.sadd(f"{root}-{child}", str(key))
