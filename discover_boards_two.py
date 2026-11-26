import json
import os
import re
import requests

SERPER_API_KEY = os.environ["SERPER_API_KEY"]
BOARDS_FILE = "boards_two.json"

QUERIES = [
    ("workable", 'site:apply.workable.com ("AI Engineer" OR "Software Engineer" OR "Full Stack") ("India" OR "Remote")'),
    ("workable", 'site:apply.workable.com ("Founding Engineer" OR "Product Engineer" OR "Backend") ("Remote" OR "Bengaluru" OR "Hyderabad")'),
    ("smartrecruiters", 'site:jobs.smartrecruiters.com ("AI Engineer" OR "Software Engineer" OR "ML Engineer") ("India" OR "Remote")'),
    ("smartrecruiters", 'site:jobs.smartrecruiters.com ("Full Stack" OR "Backend" OR "Python") ("Bengaluru" OR "Hyderabad" OR "Remote")'),
    ("rippling", 'site:ats.rippling.com ("AI Engineer" OR "Software Engineer" OR "Founding Engineer")'),
    ("rippling", 'site:ats.rippling.com ("Full Stack" OR "Backend" OR "Product Engineer") ("Remote" OR "India")'),
]

PATTERNS = {
    "workable": re.compile(r"apply\.workable\.com/([a-zA-Z0-9_-]+)"),
    "smartrecruiters": re.compile(r"jobs\.smartrecruiters\.com/([a-zA-Z0-9_-]+)"),
    "rippling": re.compile(r"ats\.rippling\.com/([a-zA-Z0-9_-]+)"),
}

IGNORE_SLUGS = {"jobs", "api", "j", "en-us", "careers", "search", "apply"}


def load_boards():
    if os.path.exists(BOARDS_FILE):
        with open(BOARDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"workable": [], "smartrecruiters": [], "rippling": []}


def discover():
    boards = load_boards()
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}

    for ats, query in QUERIES:
        existing = set(boards.get(ats, []))
        try:
            r = requests.post(
                "https://google.serper.dev/search",
                headers=headers,
                json={"q": query, "num": 20},
                timeout=20,
            )
            r.raise_for_status()
            for item in r.json().get("organic", []):
                link = item.get("link", "")
                m = PATTERNS[ats].search(link)
                if m:
                    slug = m.group(1).strip()
                    if slug.lower() not in IGNORE_SLUGS and len(slug) > 1:
                        existing.add(slug)
        except Exception as e:
            print(f"Serper error for {ats}: {e}")
        boards[ats] = sorted(existing)

    with open(BOARDS_FILE, "w", encoding="utf-8") as f:
        json.dump(boards, f, indent=2)
    print({k: len(v) for k, v in boards.items()})


if __name__ == "__main__":
    discover()
