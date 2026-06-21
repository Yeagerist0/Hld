# Search Typeahead System

A working search typeahead backend with a UI, distributed cache (consistent hashing), trending searches, and batch writes.

---

## Quick Start

```bash
# 1. Install dependencies
pip install fastapi uvicorn

# 2. Generate dataset (109,000+ queries)
python3 scripts/generate_dataset.py

# 3. Start the server
cd backend
uvicorn main:app --reload --port 8000

# 4. Open browser
open http://localhost:8000
```

---

## Interactive Dashboard (New!)

The frontend has been upgraded to **AetherSearch Console**, a premium cyberpunk-themed administrative and visualization dashboard featuring:

1. **Consistent Hash Ring Visualizer**:
   - Renders a 128-bit MD5 ring containing 450 virtual nodes (3 physical nodes × 150 virtual nodes).
   - Animates a glowing particle traveling to the key's hash position on search or suggestion hover.
   - Draws a laser beam routing the key from the circumference to its owning physical node.
   - Highlights and pulsates the active physical node on cache hits/misses.

2. **Real-time Performance Metrics**:
   - **Cache Hit Rate**: Circular progress bar showing hit-to-miss ratio.
   - **P95 Read Latency**: Latency comparison gauge.
   - **Write Reduction**: Computes exact savings from batching raw searches vs. writing unique aggregated updates.
   - **Queue Buffer Monitor**: Shows the live size of the `BatchWriter` buffer (out of 50 threshold) and pulses when a background flush transaction completes.

3. **Dual Ranking Mode Switcher**:
   - Sleek pill toggle to switch between **Basic** (overall count) and **Recency-Boosted** (trending scores).
   - Suggestions dropdown highlights matching prefix letters, and displays detailed count and score badges for transparent evaluation.

---

## Architecture

```
Browser (index.html)
    │  debounced GET /suggest?q=<prefix>  (220ms debounce)
    ▼
FastAPI (main.py)
    │
    ├─► ConsistentHashCache (cache.py)
    │       3 physical nodes × 150 virtual nodes
    │       MD5 hash ring for key → node mapping
    │       TTL = 300s, lazy expiry on read
    │       Cache HIT → return immediately
    │       Cache MISS → query SQLite, populate cache
    │
    └─► SQLite (typeahead.db)
            queries(query TEXT PK, count INTEGER)
            recent_searches(query, searched_at REAL)

POST /search → BatchWriter (batch_writer.py)
    │       in-memory buffer {query: count}
    │       flush every 50 unique entries OR 10 seconds
    └─► SQLite bulk upsert + cache invalidation
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/suggest?q=<prefix>` | Returns up to 10 prefix-matching suggestions sorted by trending score |
| POST | `/search` | Submits a search query. Returns `{"message": "Searched"}`. Count update is deferred to batch writer. |
| GET | `/trending` | Top 10 trending searches weighted by recency (last 24h) |
| GET | `/cache/debug?prefix=<p>` | Shows which cache node owns `p` and whether it's a hit or miss |
| GET | `/stats` | Cache hit rates, batch writer metrics, DB size |

---

## Data Storage

### Primary Store: SQLite (`data/typeahead.db`)
- `queries` table: `query TEXT PRIMARY KEY, count INTEGER`
- `recent_searches` table: `query TEXT, searched_at REAL` — rolling 24h window, pruned on every write
- Index on `queries(query)` for prefix scans (`LIKE 'prefix%'`)
- WAL mode for concurrent reads during batch writes

### Cache Layer: Consistent Hash Ring
- **3 physical nodes**, each replicated as **150 virtual nodes** on an MD5 hash ring
- Prefix string → MD5 hash → bisect find nearest clockwise node
- Ensures even distribution and predictable ownership per prefix key
- Entries expire after **300 seconds** (lazy eviction on read)
- On search submit, all prefix cache entries for that query are invalidated
  (e.g. submitting "python" invalidates cache keys "p", "py", "pyt", …, "python")

---

## Trending Searches

### Basic (60% marks): Sort by overall `count`
The fallback ranking used when no recent search data exists.

### Enhanced (20% marks): Recency-aware blended score

```
score = 0.4 × log(1 + count)  +  0.6 × recency_score

recency_score = Σ exp(−Δt / HALF_LIFE)
    for each search event in the last 24h
    HALF_LIFE = 6 hours
```

**How it works:**
- A search submitted 0 hours ago contributes `exp(0) = 1.0`
- A search submitted 6 hours ago contributes `exp(-1) ≈ 0.37`
- A search submitted 12 hours ago contributes `exp(-2) ≈ 0.14`
- A query popular only for a short window decays naturally — after 24h it contributes 0

**Trade-offs:**
- Freshness: up-to-the-minute recency via the 24h rolling window
- Latency: recency join is bounded (max 10,000 recent rows scanned)
- Staleness: cache TTL means trending changes take up to 300s to propagate
  (mitigated by cache invalidation on submit)

**Demo:**
```
# Before submitting searches → top result: "python" (highest all-time count)
GET /suggest?q=rust
→ ["rust", "rust tutorial", ...]

# Submit "rust tutorial" 40 times
POST /search {"query": "rust tutorial"} × 40

# After flush → "rust tutorial" outranks "rust" via recency boost
GET /suggest?q=rust
→ ["rust tutorial", "rust", ...]
```

---

## Batch Writes

Search count increments are **not written synchronously**. Instead:

1. Each `POST /search` adds the query to an in-memory `dict[str, int]`
2. The dict accumulates (repeated queries merge: count += 1)
3. A **background thread** flushes the buffer when either:
   - Buffer reaches **50 unique queries** (configurable `batch_size`)
   - **10 seconds** elapse (configurable `flush_interval`)
4. Flush issues one SQLite transaction for all accumulated counts

**Write reduction example:**
- 55 searches received with 16 unique queries → 2 DB transactions (vs 55 individual writes)
- Write reduction: ~70%

**Failure trade-off:**
If the process crashes before a flush, buffered count increments are lost. For a popularity counter this is acceptable (approximate counts are fine). For exactness, a pre-write WAL log or durable queue (e.g. Kafka) would be needed.

---

## Non-Functional Metrics

The `/stats` endpoint reports live:
- Per-node cache **hit rate**
- Total **DB reads vs cached reads**
- **Write reduction ratio** (searches buffered ÷ DB writes)
- Current batch buffer size

---

## Dataset

- **Source:** Synthetically generated from realistic search term pools (tech, products, food, travel, health, finance, entertainment)
- **Size:** 109,334 unique queries
- **Counts:** Zipf-distributed (`max_count=500,000`, `α=1.05`) — top queries have ~500k count, long tail approaches 1
- **Generation:** `python3 scripts/generate_dataset.py` (idempotent, skips if DB already populated)

---

## File Structure

```
typeahead/
├── backend/
│   ├── main.py           # FastAPI app, routes, component wiring
│   ├── database.py       # SQLite read/write operations
│   ├── cache.py          # Consistent hash ring cache
│   └── batch_writer.py   # Batch write buffer + background flusher
├── scripts/
│   └── generate_dataset.py  # Dataset generation (run once)
├── frontend/
│   └── index.html        # Single-page UI (served by FastAPI)
├── data/
│   └── typeahead.db      # SQLite database (created at runtime)
└── requirements.txt
```
