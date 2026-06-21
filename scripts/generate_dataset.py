"""
Generate 100,000+ realistic search queries with Zipf-distributed counts
and load them into the SQLite database.

Run: python scripts/generate_dataset.py
"""

import sqlite3
import math
import os
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "typeahead.db"

# ---------------------------------------------------------------------------
# Word pools
# ---------------------------------------------------------------------------

TECH_BASES = [
    "python", "javascript", "typescript", "java", "golang", "rust", "c++", "c#", "ruby", "php",
    "swift", "kotlin", "scala", "elixir", "dart", "haskell", "lua", "r programming", "julia",
    "react", "angular", "vue", "nextjs", "svelte", "nuxt", "remix", "astro", "solid",
    "nodejs", "deno", "bun", "fastapi", "django", "flask", "spring boot", "rails", "laravel", "express",
    "docker", "kubernetes", "terraform", "ansible", "jenkins", "github actions", "gitlab ci", "argocd",
    "aws", "azure", "gcp", "heroku", "vercel", "netlify", "cloudflare workers", "digitalocean",
    "mysql", "postgresql", "mongodb", "redis", "sqlite", "cassandra", "dynamodb", "firestore",
    "elasticsearch", "neo4j", "influxdb", "cockroachdb", "supabase", "planetscale",
    "machine learning", "deep learning", "neural network", "nlp", "computer vision", "llm",
    "tensorflow", "pytorch", "keras", "scikit-learn", "pandas", "numpy", "matplotlib", "huggingface",
    "git", "linux", "ubuntu", "debian", "arch linux", "fedora", "kali linux", "wsl",
    "vim", "vscode", "intellij", "pycharm", "neovim", "cursor", "zed editor",
    "api design", "rest api", "graphql", "grpc", "websocket", "oauth2", "jwt", "openid connect",
    "microservices", "serverless", "event driven", "cqrs", "ddd", "clean architecture",
    "devops", "mlops", "platform engineering", "sre", "observability", "opentelemetry",
    "react native", "flutter", "expo", "ionic", "capacitor",
    "blockchain", "smart contracts", "solidity", "web3", "defi", "ethereum",
]

PRODUCT_BASES = [
    "iphone 15", "iphone 14", "iphone 15 pro", "iphone 15 pro max", "iphone se",
    "samsung galaxy s24", "samsung galaxy s23", "samsung galaxy a54", "samsung galaxy fold",
    "google pixel 8", "google pixel 8 pro", "oneplus 12", "xiaomi 14",
    "macbook pro", "macbook air", "macbook m3", "mac mini", "imac",
    "dell xps 15", "hp spectre", "lenovo thinkpad x1", "asus zenbook", "surface pro 9",
    "airpods pro 2", "airpods max", "sony wh1000xm5", "bose quietcomfort 45", "jabra evolve2",
    "apple watch ultra", "samsung galaxy watch 6", "fitbit sense", "garmin fenix", "oura ring",
    "ipad pro", "ipad air", "samsung galaxy tab s9", "amazon fire hd",
    "sony a7iv", "canon r6", "nikon z6", "fujifilm xt5", "gopro hero 12",
    "ps5", "xbox series x", "nintendo switch oled", "steam deck", "meta quest 3",
    "amazon echo", "google nest hub", "apple homepod mini", "sonos era 100",
    "lg oled tv", "samsung qled", "sony bravia", "tcl qled",
    "dyson airwrap", "dyson v15", "roomba j9", "ecovacs deebot",
    "kindle paperwhite", "kobo libra", "remarkable 2",
]

FOOD_BASES = [
    "chocolate cake", "banana bread", "pasta carbonara", "pizza dough", "sourdough bread",
    "chicken tikka masala", "beef stew", "salmon teriyaki", "shrimp tacos", "avocado toast",
    "pancakes", "french toast", "eggs benedict", "omelette", "shakshuka",
    "caesar salad", "greek salad", "caprese salad", "pasta salad", "niçoise salad",
    "tiramisu", "cheesecake", "brownies", "macarons", "croissants",
    "butter chicken", "biryani", "pad thai", "ramen", "pho", "sushi rolls",
    "margarita cocktail", "old fashioned", "espresso martini", "matcha latte", "cold brew coffee",
    "meal prep ideas", "high protein meals", "vegan dinner", "gluten free bread", "keto snacks",
    "air fryer chicken", "instant pot rice", "slow cooker beef",
]

TRAVEL_BASES = [
    "new york", "london", "paris", "tokyo", "dubai", "singapore", "bangkok", "barcelona",
    "rome", "amsterdam", "berlin", "sydney", "toronto", "los angeles", "miami", "las vegas",
    "bali", "santorini", "maldives", "iceland", "new zealand", "costa rica", "peru",
    "cheap flights europe", "cheap flights asia", "last minute flights", "flight deals",
    "best hotels", "airbnb tips", "hostel booking", "boutique hotels",
    "travel insurance", "visa requirements", "passport renewal", "travel adapter",
    "packing list", "carry on luggage", "best travel credit card", "points and miles",
    "solo travel tips", "backpacking europe", "road trip usa", "campervan rental",
]

HEALTH_BASES = [
    "weight loss", "lose belly fat", "intermittent fasting", "keto diet", "mediterranean diet",
    "yoga for beginners", "morning yoga", "meditation for anxiety", "mindfulness",
    "full body workout", "home workout", "gym beginner", "calisthenics",
    "couch to 5k", "marathon training", "cycling for weight loss", "swimming technique",
    "better sleep", "posture fix", "back pain relief", "neck pain stretches", "hip flexor stretch",
    "protein intake", "creatine benefits", "pre workout", "collagen supplements",
    "mental health tips", "anxiety relief", "depression coping", "stress management",
]

FINANCE_BASES = [
    "bitcoin", "ethereum", "solana", "cardano", "crypto portfolio",
    "s&p 500", "index funds", "etf investing", "dividend stocks", "growth stocks",
    "compound interest", "fire movement", "retire early", "passive income",
    "budgeting app", "debt snowball", "emergency fund", "roth ira", "401k",
    "mortgage calculator", "refinance mortgage", "car loan", "student loan",
    "credit score improvement", "balance transfer card", "cashback credit card",
    "freelance taxes", "llc formation", "invoice software",
]

ENTERTAINMENT_BASES = [
    "netflix series", "hbo max shows", "disney plus movies", "amazon prime video",
    "minecraft", "fortnite", "valorant", "genshin impact", "elden ring", "baldurs gate 3",
    "spotify playlist", "apple music", "youtube music", "podcast recommendations",
    "best anime 2024", "one piece", "jujutsu kaisen", "demon slayer", "attack on titan",
    "best sci fi books", "fantasy novels", "stephen king", "book club picks",
    "photography tips", "photo editing lightroom", "video editing premiere", "content creator",
    "dnd campaign", "board games", "chess openings", "sudoku",
]

# ---------------------------------------------------------------------------
# Suffix templates (applied to every base)
# ---------------------------------------------------------------------------

SUFFIXES = [
    "", " tutorial", " tutorial for beginners", " guide", " complete guide",
    " examples", " course", " crash course", " free course", " bootcamp",
    " download", " free download", " install", " setup", " configure",
    " price", " review", " vs", " alternatives", " comparison",
    " how to", " cheat sheet", " documentation", " github", " open source",
    " for windows", " for mac", " for linux", " for android", " for ios",
    " beginner", " intermediate", " advanced", " tips", " tricks",
    " interview questions", " projects", " certification", " salary", " jobs",
    " 2022", " 2023", " 2024", " 2025", " latest",
    " best practices", " performance", " security", " testing", " deployment",
    " api", " library", " framework", " tool", " plugin",
    " online", " offline", " free", " premium", " pro version",
    " tutorial youtube", " tutorial pdf", " tutorial github", " example code",
    " vs code", " in python", " in javascript", " with docker", " on ubuntu",
    " reddit", " stackoverflow", " discord server", " community",
    " step by step", " quick start", " getting started", " introduction",
    " portfolio project", " real world project", " full stack",
    " 10 tips", " top 5", " best of 2024", " worth it", " worth learning",
    " error fix", " not working", " debug", " troubleshoot", " common mistakes",
    " roadmap", " learning path", " resources", " books", " newsletter",
    # Extended suffixes to reach 100k+ entries
    " for data science", " for web development", " for mobile", " for backend",
    " for frontend", " for devops", " for machine learning", " for beginners 2024",
    " explained", " in depth", " deep dive", " under the hood", " internals",
    " interview prep", " system design", " design patterns", " architecture",
    " best tools", " best extensions", " best plugins", " best libraries",
    " cheat sheet 2024", " cheat sheet pdf", " quick reference", " syntax guide",
    " vs rust", " vs golang", " vs python", " vs java", " vs javascript",
    " with examples", " with projects", " with source code", " hands on",
    " docker tutorial", " kubernetes tutorial", " aws tutorial", " ci cd",
    " unit testing", " integration testing", " tdd", " bdd",
    " rest api tutorial", " graphql tutorial", " websocket tutorial",
    " authentication", " authorization", " jwt tutorial", " oauth tutorial",
    " database design", " sql tutorial", " nosql tutorial", " orm tutorial",
    " microservices tutorial", " serverless tutorial", " event driven",
    " performance optimization", " caching strategies", " load balancing",
    " monitoring", " logging", " observability", " alerting",
    " open source projects", " side projects", " build from scratch",
    " resume projects", " github portfolio", " linkedin", " hackathon",
    " salary 2024", " salary usa", " salary india", " remote jobs",
    " freelance", " consultant", " startup", " big tech", " faang",
    " top 10", " top 20", " top 50", " best in 2025", " most popular",
    " what is", " why use", " when to use", " pros and cons", " benefits",
    " disadvantages", " limitations", " common errors", " gotchas",
    " memory management", " concurrency", " async", " multithreading",
    " functional programming", " object oriented", " declarative", " imperative",
    " react hooks", " state management", " redux", " context api", " zustand",
    " tailwind css", " styled components", " css modules", " sass", " bootstrap",
    " rest vs graphql", " sql vs nosql", " aws vs azure", " react vs vue",
    " for production", " production ready", " scalable", " maintainable",
    " open ai api", " chatgpt api", " llm integration", " ai features",
    " latest version", " upgrade guide", " migration guide", " changelog",
    " community edition", " enterprise edition", " cloud edition",
    " january 2024", " february 2024", " march 2024", " april 2024",
    " may 2024", " june 2024", " july 2024", " august 2024",
    " september 2024", " october 2024", " november 2024", " december 2024",
    " january 2025", " february 2025", " march 2025", " april 2025",
    " q1 2024", " q2 2024", " q3 2024", " q4 2024", " q1 2025",
    " week 1", " week 2", " day 1", " day 30", " 30 day challenge",
    " for kids", " for students", " for professionals", " for seniors",
    " crash course 2024", " full course", " mini course", " nano course",
    " project ideas", " capstone project", " final project", " thesis",
    " cli", " gui", " web app", " desktop app", " chrome extension",
    " automation", " scripting", " shell script", " batch script",
    " windows 11", " macos ventura", " ubuntu 24.04", " wsl2",
    " m1 mac", " m2 mac", " apple silicon", " arm64",
    " with ai", " with chatgpt", " with copilot", " ai powered",
    " low code", " no code", " visual builder", " drag and drop",
    " free tier", " free plan", " pricing", " cost comparison", " roi",
    " tutorial 2025", " guide 2025", " course 2025", " tips 2025",
]

# ---------------------------------------------------------------------------
# Dataset generation
# ---------------------------------------------------------------------------

ALL_BASES = (
    TECH_BASES + PRODUCT_BASES + FOOD_BASES + TRAVEL_BASES
    + HEALTH_BASES + FINANCE_BASES + ENTERTAINMENT_BASES
)


def zipf_count(rank: int, max_count: int = 500_000, alpha: float = 1.05) -> int:
    return max(1, int(max_count / (rank ** alpha)))


def generate_queries() -> list[tuple[str, int]]:
    seen: dict[str, int] = {}
    rank = 1
    for base in ALL_BASES:
        for suffix in SUFFIXES:
            q = f"{base}{suffix}".strip()
            if q not in seen:
                seen[q] = zipf_count(rank)
                rank += 1

    # Add cross-pair "X vs Y" queries
    tech_short = TECH_BASES[:40]
    product_short = PRODUCT_BASES[:20]
    for i, b1 in enumerate(tech_short):
        for b2 in tech_short[i + 1: i + 4]:
            q = f"{b1} vs {b2}"
            if q not in seen:
                seen[q] = zipf_count(rank)
                rank += 1
    for i, b1 in enumerate(product_short):
        for b2 in product_short[i + 1: i + 4]:
            q = f"{b1} vs {b2}"
            if q not in seen:
                seen[q] = zipf_count(rank)
                rank += 1

    # Add "how to learn X" and "learn X" variants
    for base in TECH_BASES + HEALTH_BASES:
        for tmpl in [f"how to learn {base}", f"learn {base} fast", f"best way to learn {base}"]:
            if tmpl not in seen:
                seen[tmpl] = zipf_count(rank)
                rank += 1

    return list(seen.items())


def main():
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
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

    existing = conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
    if existing > 0:
        print(f"Database already has {existing:,} queries. Skipping generation.")
        print("Delete data/typeahead.db to regenerate.")
        conn.close()
        return

    print("Generating dataset...")
    queries = generate_queries()
    print(f"  Generated {len(queries):,} unique queries.")

    BATCH = 5000
    for i in range(0, len(queries), BATCH):
        batch = queries[i: i + BATCH]
        conn.executemany(
            "INSERT OR IGNORE INTO queries (query, count) VALUES (?, ?)", batch
        )
        conn.commit()
        pct = min(100, int((i + BATCH) / len(queries) * 100))
        print(f"  Inserted {min(i + BATCH, len(queries)):,}/{len(queries):,} ({pct}%)", end="\r")

    final_count = conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
    print(f"\nDone. {final_count:,} queries in database.")
    conn.close()


if __name__ == "__main__":
    main()
