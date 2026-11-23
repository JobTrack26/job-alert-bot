"""Export readable titles, locations, and direct links from seen_jobs.json.

Usage:
    python export_seen_jobs.py
    python export_seen_jobs.py --input seen_jobs.json --output seen_jobs_links.txt
    python export_seen_jobs.py --skip-senior
    python export_seen_jobs.py --no-fetch
"""

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import requests

HEADERS = {"User-Agent": "JobAlertBot/1.0"}
SENIOR_TERMS = (
    "senior", "sr.", "sr ", "staff", "principal", "lead",
    "manager", "director", "head of", "vp ", "architect",
)


def parse_seen_ids(seen_ids):
    ats_grouped = defaultdict(set)
    yc_ids = []
    reddit_ids = []

    for raw in seen_ids:
        parts = raw.split(":", 2)
        prefix = parts[0]
        if prefix in ("ashby", "gh", "lever") and len(parts) == 3:
            ats_grouped[(prefix, parts[1])].add(parts[2])
        elif prefix == "yc" and len(parts) >= 2:
            yc_ids.append(parts[1])
        elif prefix == "reddit" and len(parts) >= 2:
            reddit_ids.append(parts[1])

    return ats_grouped, yc_ids, reddit_ids


def fallback_url(prefix, slug, job_id):
    if prefix == "ashby":
        return f"https://jobs.ashbyhq.com/{slug}/{job_id}"
    if prefix == "gh":
        return f"https://job-boards.greenhouse.io/{slug}/jobs/{job_id}"
    if prefix == "lever":
        return f"https://jobs.lever.co/{slug}/{job_id}"
    if prefix == "yc":
        return f"https://news.ycombinator.com/item?id={job_id}"
    if prefix == "reddit":
        return f"https://reddit.com/comments/{job_id}"
    return ""


def fetch_ats_board(item):
    (ats, slug), target_ids = item
    results = []
    matched_ids = set()

    try:
        if ats == "ashby":
            r = requests.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                headers=HEADERS,
                timeout=12,
            )
            if r.status_code == 200:
                for j in r.json().get("jobs", []):
                    jid = str(j.get("id", ""))
                    if jid in target_ids:
                        matched_ids.add(jid)
                        title = j.get("title", "Untitled")
                        loc = j.get("location", "")
                        url = j.get("jobUrl") or fallback_url("ashby", slug, jid)
                        results.append((f"Ashby · {slug}", title, loc, url, True))
        elif ats == "greenhouse" or ats == "gh":
            r = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                headers=HEADERS,
                timeout=12,
            )
            if r.status_code == 200:
                for j in r.json().get("jobs", []):
                    jid = str(j.get("id", ""))
                    if jid in target_ids:
                        matched_ids.add(jid)
                        title = j.get("title", "Untitled")
                        loc = (j.get("location") or {}).get("name", "")
                        url = j.get("absolute_url") or fallback_url("gh", slug, jid)
                        results.append((f"Greenhouse · {slug}", title, loc, url, True))
        elif ats == "lever":
            r = requests.get(
                f"https://api.lever.co/v0/postings/{slug}?mode=json",
                headers=HEADERS,
                timeout=12,
            )
            if r.status_code == 200:
                for j in r.json():
                    jid = str(j.get("id", ""))
                    if jid in target_ids:
                        matched_ids.add(jid)
                        title = j.get("text", "Untitled")
                        loc = (j.get("categories") or {}).get("location", "")
                        url = j.get("hostedUrl") or fallback_url("lever", slug, jid)
                        results.append((f"Lever · {slug}", title, loc, url, True))
    except Exception:
        pass

    expired_count = len(target_ids - matched_ids)
    return results, expired_count


def fetch_yc_item(item_id):
    try:
        r = requests.get(
            f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json",
            timeout=10,
        )
        if r.status_code == 200 and r.json():
            item = r.json()
            title = item.get("title", f"YC Job #{item_id}")
            url = item.get("url") or fallback_url("yc", "", item_id)
            return ("YC / HN", title, "", url, True)
    except Exception:
        pass
    return ("YC / HN", f"YC Job #{item_id}", "", fallback_url("yc", "", item_id), False)


def fetch_reddit_item(post_id):
    try:
        r = requests.get(
            f"https://www.reddit.com/comments/{post_id}.json",
            headers={"User-Agent": "python:job-alert-bot:v1.0"},
            timeout=12,
        )
        if r.status_code == 200:
            data = r.json()[0]["data"]["children"][0]["data"]
            sub = data.get("subreddit", "reddit")
            title = data.get("title", f"Reddit Post {post_id}")
            url = f"https://reddit.com{data['permalink']}"
            return (f"Referral · r/{sub}", title, "", url, True)
    except Exception:
        pass
    return ("Reddit", f"Post {post_id}", "", fallback_url("reddit", "", post_id), False)


def is_senior_title(title):
    low = title.lower()
    return any(term in low for term in SENIOR_TERMS)


def main():
    parser = argparse.ArgumentParser(
        description="Resolve seen_jobs.json IDs into readable titles, locations, and links."
    )
    parser.add_argument("--input", default="seen_jobs.json", help="Path to seen_jobs.json")
    parser.add_argument("--output", default="seen_jobs_links.txt", help="Output text file")
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Reconstruct URLs offline without calling ATS/HN/Reddit APIs",
    )
    parser.add_argument(
        "--skip-senior",
        action="store_true",
        help="Exclude obvious Senior/Staff/Principal/Lead/Manager titles",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"File not found: {input_path}")

    seen_ids = json.loads(input_path.read_text(encoding="utf-8"))
    ats_grouped, yc_ids, reddit_ids = parse_seen_ids(seen_ids)

    rows = []
    expired_ats = 0

    if args.no_fetch:
        for (ats, slug), jids in sorted(ats_grouped.items()):
            label = {"ashby": "Ashby", "gh": "Greenhouse", "lever": "Lever"}[ats]
            for jid in sorted(jids):
                rows.append((f"{label} · {slug}", jid, "", fallback_url(ats, slug, jid)))
        for item_id in yc_ids:
            rows.append(("YC / HN", f"YC Job #{item_id}", "", fallback_url("yc", "", item_id)))
        for post_id in reddit_ids:
            rows.append(("Reddit", f"Post {post_id}", "", fallback_url("reddit", "", post_id)))
    else:
        with ThreadPoolExecutor(max_workers=20) as pool:
            for batch, exp in pool.map(fetch_ats_board, ats_grouped.items()):
                expired_ats += exp
                for src, title, loc, url, _ in batch:
                    rows.append((src, title, loc, url))

            for src, title, loc, url, _ in pool.map(fetch_yc_item, yc_ids):
                rows.append((src, title, loc, url))

            for src, title, loc, url, _ in pool.map(fetch_reddit_item, reddit_ids):
                rows.append((src, title, loc, url))

    if args.skip_senior:
        rows = [r for r in rows if not is_senior_title(r[1])]

    lines = []
    for i, (src, title, loc, url) in enumerate(rows, 1):
        label = f"{title} ({loc})" if loc else title
        lines.append(f"{i}. [{src}] {label}\n   {url}")

    output_path = Path(args.output)
    output_path.write_text("\n\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    print(f"Total IDs in {input_path.name}: {len(seen_ids)}")
    if not args.no_fetch:
        print(f"Expired/closed ATS listings skipped: {expired_ats}")
    print(f"Exported {len(rows)} listings -> {output_path}")


if __name__ == "__main__":
    main()