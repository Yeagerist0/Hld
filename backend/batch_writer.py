"""
Batch write buffer for search-count updates.

Design:
- Search submissions accumulate in an in-memory dict {query: count}.
- Repeated identical queries within a flush window are merged (aggregated).
- A background daemon thread flushes on a configurable interval.
- Flush is also triggered when the buffer reaches BATCH_SIZE unique entries.
- On flush, the entire snapshot is written to the DB in one transaction.

Failure trade-off:
- If the process crashes before a flush, buffered increments are lost.
- This is acceptable for a popularity counter (approximate is fine).
- For exactness, a WAL/log could persist the buffer, but that complexity
  is out of scope for this assignment demo.
"""

import threading
import time
from collections import defaultdict
from typing import Callable


class BatchWriter:
    def __init__(
        self,
        flush_fn: Callable[[dict[str, int]], None],
        batch_size: int = 50,
        flush_interval: float = 10.0,
    ):
        self._buffer: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()
        self._flush_fn = flush_fn
        self._batch_size = batch_size
        self._flush_interval = flush_interval

        # Metrics
        self._total_buffered = 0
        self._total_db_writes = 0
        self._flush_count = 0

        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="batch-flusher")
        self._thread.start()

    def add(self, query: str):
        with self._lock:
            self._buffer[query] += 1
            self._total_buffered += 1
            if len(self._buffer) >= self._batch_size:
                self._flush_locked()

    def _flush_locked(self):
        if not self._buffer:
            return
        snapshot = dict(self._buffer)
        self._buffer.clear()
        self._flush_count += 1
        self._total_db_writes += len(snapshot)
        # Release lock before calling DB (may block)
        self._lock.release()
        try:
            self._flush_fn(snapshot)
        finally:
            self._lock.acquire()

    def flush(self):
        with self._lock:
            self._flush_locked()

    def _loop(self):
        while not self._stop.wait(self._flush_interval):
            with self._lock:
                self._flush_locked()

    def stop(self):
        self._stop.set()
        self.flush()

    def stats(self) -> dict:
        with self._lock:
            buffered = self._total_buffered
            db = self._total_db_writes
            reduction = round(1 - db / buffered, 3) if buffered else 0.0
            return {
                "total_searches_received": buffered,
                "total_unique_queries_written_to_db": db,
                "total_batch_flushes": self._flush_count,
                "write_reduction_ratio": reduction,
                "current_buffer_size": len(self._buffer),
                "batch_size_threshold": self._batch_size,
                "flush_interval_seconds": self._flush_interval,
            }
