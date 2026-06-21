import sqlite3
import os
import time
import math
import threading
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "typeahead.db"
_local = threading.local()


def get_conn():
    if not hasattr(_local, "conn"):
        os.makedirs(DB_PATH.parent, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
    return _local.conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS queries (
            query TEXT PRIMARY KEY,
            count INTEGER DEFAULT 1
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_query ON queries(query)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recent_searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            searched_at REAL NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rs_query ON recent_searches(query)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rs_time ON recent_searches(searched_at)")
    conn.commit()


def get_query_count() -> int:
    return get_conn().execute("SELECT COUNT(*) as c FROM queries").fetchone()["c"]


def get_suggestions_basic(prefix: str, limit: int = 10) -> list[dict]:
    rows = get_conn().execute(
        "SELECT query, count FROM queries WHERE query LIKE ? ORDER BY count DESC LIMIT ?",
        (f"{prefix}%", limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_suggestions_trending(prefix: str, limit: int = 10) -> list[dict]:
    """
    Blended score = 0.4 * log(1 + count) + 0.6 * recency_score

    recency_score = sum of exp(-delta / HALF_LIFE) for each recent search.
    HALF_LIFE = 6 hours: a search done 6h ago contributes ~0.5, 12h ago ~0.25.
    This boosts recently-active queries without permanently over-ranking
    queries that were only hot for a short window.
    Cache is invalidated per-prefix whenever a new search is submitted.
    """
    conn = get_conn()
    now = time.time()
    HALF_LIFE = 6 * 3600
    cutoff = now - 86400  # 24-hour window

    candidates = conn.execute(
        "SELECT query, count FROM queries WHERE query LIKE ? ORDER BY count DESC LIMIT 200",
        (f"{prefix}%",),
    ).fetchall()

    if not candidates:
        return []

    candidate_queries = tuple(r["query"] for r in candidates)
    placeholders = ",".join("?" * len(candidate_queries))

    recent_rows = conn.execute(
        f"SELECT query, searched_at FROM recent_searches "
        f"WHERE query IN ({placeholders}) AND searched_at > ?",
        list(candidate_queries) + [cutoff],
    ).fetchall()

    recency: dict[str, float] = {}
    for r in recent_rows:
        decay = math.exp(-(now - r["searched_at"]) / HALF_LIFE)
        recency[r["query"]] = recency.get(r["query"], 0.0) + decay

    scored = []
    for row in candidates:
        q = row["query"]
        score = 0.4 * math.log1p(row["count"]) + 0.6 * recency.get(q, 0.0)
        scored.append({"query": q, "count": row["count"], "score": round(score, 4)})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def bulk_increment(updates: dict[str, int]):
    """Batch upsert: increment counts for multiple queries atomically."""
    conn = get_conn()
    for query, delta in updates.items():
        conn.execute(
            "INSERT INTO queries (query, count) VALUES (?, ?) "
            "ON CONFLICT(query) DO UPDATE SET count = count + ?",
            (query, delta, delta),
        )
    conn.commit()


def add_recent_searches(queries: list[str]):
    """Record recent search events (used for recency scoring)."""
    conn = get_conn()
    now = time.time()
    conn.executemany(
        "INSERT INTO recent_searches (query, searched_at) VALUES (?, ?)",
        [(q, now) for q in queries],
    )
    # Prune entries older than 24h
    conn.execute("DELETE FROM recent_searches WHERE searched_at < ?", (now - 86400,))
    conn.commit()


def get_trending_global(limit: int = 10) -> list[dict]:
    """Trending queries ranked by recency-weighted score (last 24h)."""
    conn = get_conn()
    now = time.time()
    HALF_LIFE = 6 * 3600
    cutoff = now - 86400

    recent = conn.execute(
        "SELECT query, searched_at FROM recent_searches WHERE searched_at > ? "
        "ORDER BY searched_at DESC LIMIT 10000",
        (cutoff,),
    ).fetchall()

    if not recent:
        rows = conn.execute(
            "SELECT query, count FROM queries ORDER BY count DESC LIMIT ?", (limit,)
        ).fetchall()
        return [{"query": r["query"], "count": r["count"]} for r in rows]

    scores: dict[str, float] = {}
    for r in recent:
        scores[r["query"]] = scores.get(r["query"], 0.0) + math.exp(
            -(now - r["searched_at"]) / HALF_LIFE
        )

    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [{"query": q, "score": round(s, 3)} for q, s in top]
