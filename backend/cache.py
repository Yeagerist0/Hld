"""
Distributed in-memory cache using a consistent hash ring.

Architecture:
- 3 physical cache nodes, each with 150 virtual nodes on the ring.
- Prefix keys are hashed (MD5) to locate their owning node.
- Ensures even key distribution and stable node ownership when nodes are added/removed.
- Each entry has a TTL; expired entries are evicted lazily on read.
"""

import hashlib
import bisect
import time
import threading
from typing import Any, Optional


class _Node:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.store: dict[str, tuple[Any, float]] = {}  # key -> (value, expires_at)
        self.hits = 0
        self.misses = 0


class ConsistentHashCache:
    def __init__(self, num_nodes: int = 3, vnodes: int = 150, ttl: int = 300):
        self._ttl = ttl
        self._ring: dict[int, str] = {}
        self._sorted_keys: list[int] = []
        self._nodes: dict[str, _Node] = {}
        self._lock = threading.RLock()

        for i in range(num_nodes):
            self._add_node(f"cache_node_{i}")

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def _add_node(self, node_id: str):
        self._nodes[node_id] = _Node(node_id)
        for i in range(150):  # 150 virtual nodes per physical node
            vkey = self._hash(f"{node_id}#vn{i}")
            self._ring[vkey] = node_id
            bisect.insort(self._sorted_keys, vkey)

    def _get_node_id(self, key: str) -> str:
        h = self._hash(key)
        idx = bisect.bisect_right(self._sorted_keys, h) % len(self._sorted_keys)
        return self._ring[self._sorted_keys[idx]]

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            node = self._nodes[self._get_node_id(key)]
            entry = node.store.get(key)
            if entry is None or entry[1] < time.time():
                node.misses += 1
                if entry:
                    del node.store[key]
                return None
            node.hits += 1
            return entry[0]

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        with self._lock:
            node = self._nodes[self._get_node_id(key)]
            node.store[key] = (value, time.time() + (ttl or self._ttl))

    def delete(self, key: str):
        with self._lock:
            node = self._nodes[self._get_node_id(key)]
            node.store.pop(key, None)

    def invalidate_for_query(self, query: str):
        """Invalidate all prefix cache entries that match this query."""
        with self._lock:
            if ":" in query:
                prefix_type, actual_query = query.split(":", 1)
                for length in range(1, len(actual_query) + 1):
                    prefix = f"{prefix_type}:{actual_query[:length]}"
                    node = self._nodes[self._get_node_id(prefix)]
                    node.store.pop(prefix, None)
            else:
                for length in range(1, len(query) + 1):
                    prefix = query[:length]
                    node = self._nodes[self._get_node_id(prefix)]
                    node.store.pop(prefix, None)

    def debug(self, prefix: str) -> dict:
        with self._lock:
            node_id = self._get_node_id(prefix)
            node = self._nodes[node_id]
            entry = node.store.get(prefix)
            now = time.time()
            is_hit = entry is not None and entry[1] >= now
            return {
                "prefix": prefix,
                "node": node_id,
                "hit": is_hit,
                "expires_in_seconds": round(entry[1] - now, 1) if is_hit else None,
                "ring_hash": self._hash(prefix),
            }

    def stats(self) -> dict:
        with self._lock:
            result = {}
            for node_id, node in self._nodes.items():
                total = node.hits + node.misses
                now = time.time()
                live_keys = sum(1 for v in node.store.values() if v[1] >= now)
                result[node_id] = {
                    "hits": node.hits,
                    "misses": node.misses,
                    "hit_rate": round(node.hits / total, 3) if total else 0.0,
                    "live_cached_keys": live_keys,
                }
            return result
