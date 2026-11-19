import json
import os
import re
from pathlib import Path
import requests

SERPER_API_KEY = os.environ["SERPER_API_KEY"]

BOARDS_FILE = Path("boards.json")
STATE_FILE = Path("discover_state.json")

SEED_BOARDS = {
    "ashby": ["bolna", "supabase", "Mastra", "linear", "elevenlabs", "perplexity", "replit", "posthog", "langfuse"],
    "greenhouse": ["stripe", "anthropic", "scaleai", "vercel", "postman", "razorpay", "browserstack", "datadog"],
    "lever": ["palantir", "mistral", "netflix", "spotify", "welocalize"],
}

DISCOVERY_QUERIES = {
    "ashby": [
        'site:jobs.ashbyhq.com ("AI Engineer" OR "Founding Engineer") ("India" OR "Bengaluru" OR "Remote")',
        'site:jobs.ashbyhq.com ("LLM" OR "AI Agents" OR "Full Stack") ("Python" OR "TypeScript")',
    ],
    "greenhouse": [
        '(site:boards.greenhouse.io OR site:job-boards.greenhouse.io) ("AI Engineer" OR "Founding Engineer") ("India" OR "Bengaluru" OR "Remote")',
        '(site:boards.greenhouse.io OR site:job-boards.greenhouse.io) ("Backend" OR "Platform Engineer") ("Python" OR "TypeScript") ("India" OR "Remote")',
    ],
    "lever": [
        'site:jobs.lever.co ("AI Engineer" OR "Founding Engineer") ("India" OR "Bengaluru" OR "Remote")',
        'site:jobs.lever.co ("Full Stack" OR "Backend Engineer") ("Python" OR "TypeScript") ("India" OR "Remote")',
    ],
}

URL_PATTERNS = {
    "ashby": r"jobs\.ashbyhq\.com/([^/?#]+)",
    "greenhouse": r"(?:boards|job-boards)\.greenhouse\.io/([^/?#]+)",
    "lever": r"jobs\.lever\.co/([^/?#]+)",
}

SKIP_SLUGS = {"embed", "api", "static", "assets", "jobs", "apply"}


def load_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def extract_slug(ats, url):
    match = re.search(URL_PATTERNS[ats], url, re.IGNORECASE)
    if not match:
        return None
    slug = match.group(1).strip()
    return None if slug.lower() in SKIP_SLUGS else slug


def verify_slug(ats, slug):
    try:
        if ats == "ashby":
            r = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", timeout=10)
            return r.status_code == 200 and "jobs" in r.json()
        if ats == "greenhouse":
            r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", timeout=10)
            return r.status_code == 200 and "jobs" in r.json()
        if ats == "lever":
            r = requests.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", timeout=10)
            return r.status_code == 200 and isinstance(r.json(), list)
    except Exception:
        return False
    return False


def serper_search(query, page=1):
    r = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        json={"q": query, "num": 20, "page": page},
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("organic", [])


def main():
    boards = load_json(BOARDS_FILE, SEED_BOARDS)
    state = load_json(STATE_FILE, {"pages": {}})

    for ats, queries in DISCOVERY_QUERIES.items():
        boards.setdefault(ats, [])
        seen_lower = {s.lower() for s in boards[ats]}
        added = []

        for query in queries:
            page = state["pages"].get(query, 1)
            results = serper_search(query, page=page)
            state["pages"][query] = page + 1 if results else 1

            for item in results:
                slug = extract_slug(ats, item.get("link", ""))
                if not slug or slug.lower() in seen_lower:
                    continue
                if verify_slug(ats, slug):
                    boards[ats].append(slug)
                    seen_lower.add(slug.lower())
                    added.append(slug)

        boards[ats] = sorted(boards[ats], key=str.lower)
        print(f"[{ats}] Added {len(added)} new slugs: {added}")

    save_json(BOARDS_FILE, boards)
    save_json(STATE_FILE, state)


if __name__ == "__main__":
    main()
