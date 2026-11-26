import json
import os
import re
import requests

SERPER_API_KEY = os.environ["SERPER_API_KEY"]
BOARDS_FILE = "boards_two.json"

QUERIES = [
    ("workable", 'site:apply.workable.com "AI Engineer" remote'),
    ("workable", 'site:apply.workable.com "Software Engineer" India'),
    ("workable", 'site:apply.workable.com "Full Stack" remote'),
    ("smartrecruiters", 'site:jobs.smartrecruiters.com "AI Engineer" India'),
    ("smartrecruiters", 'site:jobs.smartrecruiters.com "Software Engineer" Bengaluru'),
    ("smartrecruiters", 'site:jobs.smartrecruiters.com "Backend Engineer" remote'),
    ("rippling", 'site:ats.rippling.com "AI Engineer"'),
    ("rippling", 'site:ats.rippling.com "Software Engineer" remote'),
    ("rippling", 'site:ats.rippling.com "Founding Engineer"'),
    ("recruitee", 'site:recruitee.com "AI Engineer" remote'),
    ("recruitee", 'site:recruitee.com "Software Engineer" remote'),
    ("teamtailor", 'site:teamtailor.com "Software Engineer" remote'),
    ("teamtailor", 'site:teamtailor.com "AI Engineer" remote'),
    ("pinpoint", 'site:pinpointhq.com "Software Engineer" remote'),
    ("breezy", 'site:breezy.hr "Software Engineer" remote'),
]

PATTERNS = {
    "workable": re.compile(r"apply\.workable\.com/([a-zA-Z0-9_-]+)"),
    "smartrecruiters": re.compile(r"jobs\.smartrecruiters\.com/([a-zA-Z0-9_-]+)"),
    "rippling": re.compile(r"ats\.rippling\.com/([a-zA-Z0-9_-]+)"),
    "recruitee": re.compile(r"https?://([a-zA-Z0-9_-]+)\.recruitee\.com"),
    "teamtailor": re.compile(r"https?://([a-zA-Z0-9_-]+)\.teamtailor\.com"),
    "pinpoint": re.compile(r"https?://([a-zA-Z0-9_-]+)\.pinpointhq\.com"),
    "breezy": re.compile(r"https?://([a-zA-Z0-9_-]+)\.breezy\.hr"),
}

IGNORE_SLUGS = {
    "jobs", "api", "j", "en-us", "careers", "search", "apply",
    "www", "app", "docs", "support", "help", "blog", "career",
}


def load_boards():
    default = {k: [] for k in PATTERNS}
    if os.path.exists(BOARDS_FILE):
        with open(BOARDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k in default:
                data.setdefault(k, [])
            return data
    return default


def discover():
    boards = load_boards()
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}

    for ats, query in QUERIES:
        existing = set(boards.get(ats, []))
        try:
            r = requests.post(
                "https://google.serper.dev/search",
                headers=headers,
                json={"q": query, "num": 10},
                timeout=20,
            )
            if r.status_code != 200:
                print(f"Serper {r.status_code} for {ats} ({query}): {r.text}")
                continue
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
