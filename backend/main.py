import time
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from database import (
    add_recent_searches,
    bulk_increment,
    get_query_count,
    get_suggestions_trending,
    get_trending_global,
    init_db,
)
from cache import ConsistentHashCache
from batch_writer import BatchWriter

app = FastAPI(title="Search Typeahead System", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FRONTEND = Path(__file__).parent.parent / "frontend" / "index.html"

# ---------------------------------------------------------------------------
# System components
# ---------------------------------------------------------------------------

init_db()
cache = ConsistentHashCache(num_nodes=3, vnodes=150, ttl=300)


def _on_flush(updates: dict[str, int]):
    """Flush handler: write counts + recency records, then invalidate cache."""
    bulk_increment(updates)
    add_recent_searches(list(updates.keys()))
    for query in updates:
        cache.invalidate_for_query(f"basic:{query}")
        cache.invalidate_for_query(f"trending:{query}")


batch_writer = BatchWriter(flush_fn=_on_flush, batch_size=50, flush_interval=10.0)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse(str(FRONTEND))


@app.get("/index.css")
async def get_css():
    return FileResponse(str(FRONTEND.parent / "index.css"))


@app.get("/suggest")
async def suggest(q: str = Query(default=""), mode: str = Query(default="trending")):
    """
    Return up to 10 suggestions for the given prefix.
    Check cache first (consistent-hash node lookup).
    On miss, query DB with trending-aware scoring and populate cache.
    """
    prefix = q.strip().lower()
    if not prefix:
        return {"suggestions": [], "source": "none"}

    cache_key = f"{mode}:{prefix}"
    cached = cache.get(cache_key)
    if cached is not None:
        return {"suggestions": cached, "source": "cache"}

    t0 = time.perf_counter()
    if mode == "basic":
        results = get_suggestions_basic(prefix)
    else:
        results = get_suggestions_trending(prefix)
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    cache.set(cache_key, results)

    return {"suggestions": results, "source": "database", "latency_ms": latency_ms}


class SearchBody(BaseModel):
    query: str


@app.post("/search")
async def search(body: SearchBody):
    """
    Submit a search. Returns dummy 'Searched' response.
    Count increment is deferred to batch writer (non-blocking).
    """
    query = body.query.strip().lower()
    if query:
        batch_writer.add(query)
    return {"message": "Searched", "query": query}


@app.get("/trending")
async def trending():
    return {"trending": get_trending_global(limit=10)}


@app.get("/cache/debug")
async def cache_debug(prefix: str = Query(...), mode: str = Query(default="trending")):
    """Show which cache node owns this prefix and whether it's a hit or miss."""
    cache_key = f"{mode}:{prefix.strip().lower()}"
    return cache.debug(cache_key)


@app.get("/cache/ring")
async def cache_ring():
    """Return the sorted ring keys and physical node mapping for visualization."""
    with cache._lock:
        return {
            "sorted_keys": cache._sorted_keys,
            "ring": cache._ring
        }


@app.get("/stats")
async def stats():
    return {
        "cache": cache.stats(),
        "batch_writer": batch_writer.stats(),
        "database": {"total_queries": get_query_count()},
    }
