from concurrent.futures import ThreadPoolExecutor
import html
import json
import os
from pathlib import Path
import requests
from email.message import EmailMessage
import smtplib


TG_TOKEN = os.environ["TG_BOT_TOKEN"]
TG_CHAT_ID = os.environ["TG_CHAT_ID"]

ROLE_KEYWORDS = [
    "ai", "llm", "agent", "founding", "full stack", "fullstack",
    "backend", "platform", "software engineer", "solutions engineer",
    "python", "typescript", "voice", "ml",
]

LOCATION_KEYWORDS = [
    "india", "bengaluru", "bangalore", "hyderabad", "delhi",
    "gurugram", "remote", "anywhere", "apac",
]

BOARDS_FILE = Path("boards.json")
STATE_FILE = Path("seen_jobs.json")
HEADERS = {"User-Agent": "JobAlertBot/1.0"}


def load_seen():
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    return set()


def save_seen(seen):
    STATE_FILE.write_text(json.dumps(sorted(seen), indent=2), encoding="utf-8")


def load_boards():
    if BOARDS_FILE.exists():
        return json.loads(BOARDS_FILE.read_text(encoding="utf-8"))
    return {
        "ashby": ["bolna", "supabase", "Mastra", "linear", "elevenlabs"],
        "greenhouse": ["stripe", "anthropic", "vercel", "postman"],
        "lever": ["mistral", "palantir"],
    }


def matches_filters(text, check_location=True):
    low = text.lower()
    role_ok = any(k in low for k in ROLE_KEYWORDS)
    loc_ok = (not check_location) or any(k in low for k in LOCATION_KEYWORDS)
    return role_ok and loc_ok


def _poll_board(task):
    ats, slug = task
    jobs_out = []
    try:
        if ats == "ashby":
            r = requests.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                headers=HEADERS,
                timeout=10,
            )
            if r.status_code == 200:
                for j in r.json().get("jobs", []):
                    jobs_out.append((
                        f"ashby:{slug}:{j.get('id')}",
                        f"Ashby · {slug}",
                        j.get("title", ""),
                        j.get("location", ""),
                        j.get("jobUrl", f"https://jobs.ashbyhq.com/{slug}"),
                    ))
        elif ats == "greenhouse":
            r = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                headers=HEADERS,
                timeout=10,
            )
            if r.status_code == 200:
                for j in r.json().get("jobs", []):
                    loc = (j.get("location") or {}).get("name", "")
                    jobs_out.append((
                        f"gh:{slug}:{j.get('id')}",
                        f"Greenhouse · {slug}",
                        j.get("title", ""),
                        loc,
                        j.get("absolute_url", f"https://boards.greenhouse.io/{slug}"),
                    ))
        elif ats == "lever":
            r = requests.get(
                f"https://api.lever.co/v0/postings/{slug}?mode=json",
                headers=HEADERS,
                timeout=10,
            )
            if r.status_code == 200:
                for j in r.json():
                    loc = (j.get("categories") or {}).get("location", "")
                    jobs_out.append((
                        f"lever:{slug}:{j.get('id')}",
                        f"Lever · {slug}",
                        j.get("text", ""),
                        loc,
                        j.get("hostedUrl", f"https://jobs.lever.co/{slug}"),
                    ))
    except Exception:
        pass
    return jobs_out


def fetch_all_ats_jobs(seen):
    boards = load_boards()
    tasks = [(ats, slug) for ats, slugs in boards.items() for slug in slugs]
    found = []

    with ThreadPoolExecutor(max_workers=20) as pool:
        for batch in pool.map(_poll_board, tasks):
            for job_id, source, title, loc, url in batch:
                if job_id in seen:
                    continue
                if matches_filters(f"{title} {loc}"):
                    seen.add(job_id)
                    found.append((source, f"{title} ({loc})" if loc else title, url))
    return found


def fetch_yc_jobs(seen):
    found = []
    try:
        ids = requests.get(
            "https://hacker-news.firebaseio.com/v0/jobstories.json",
            timeout=15,
        ).json()[:30]
        for item_id in ids:
            key = f"yc:{item_id}"
            if key in seen:
                continue
            item = requests.get(
                f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json",
                timeout=10,
            ).json()
            if not item:
                continue
            title = item.get("title", "")
            url = item.get("url") or f"https://news.ycombinator.com/item?id={item_id}"
            if matches_filters(title, check_location=False):
                seen.add(key)
                found.append(("YC / HN", title, url))
    except Exception:
        pass
    return found


def fetch_referrals(seen):
    found = []
    subreddits = ["developersIndia", "hiring", "RemoteJobs"]
    for sub in subreddits:
        try:
            r = requests.get(
                f"https://www.reddit.com/r/{sub}/new.json?limit=20",
                headers={"User-Agent": "python:job-alert-bot:v1.0"},
                timeout=15,
            )
            if r.status_code != 200:
                continue
            for post in r.json().get("data", {}).get("children", []):
                d = post["data"]
                key = f"reddit:{d['id']}"
                if key in seen:
                    continue
                title = d.get("title", "")
                low = title.lower()
                if ("referral" in low or "hiring" in low) and matches_filters(title, check_location=False):
                    seen.add(key)
                    found.append((f"Referral · r/{sub}", title, f"https://reddit.com{d['permalink']}"))
        except Exception:
            continue
    return found


def send_telegram(text):
    requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        json={
            "chat_id": TG_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=20,
    ).raise_for_status()

def send_jobs_email(alerts):
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not app_password or not alerts:
        return

    sender = "nimeshchandhra2005@gmail.com"
    recipients = "nimeshchandhra2005+jobs@gmail.com"

    lines = [
        f"{i}. [{src}] {title}\n   {url}"
        for i, (src, title, url) in enumerate(alerts, 1)
    ]

    msg = EmailMessage()
    msg["Subject"] = "[Job Alert Bot] New Listings"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content("\n\n".join(lines))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, app_password)
        smtp.send_message(msg)

def main():
    seen = load_seen()
    alerts = []
    alerts.extend(fetch_all_ats_jobs(seen))
    alerts.extend(fetch_yc_jobs(seen))
    alerts.extend(fetch_referrals(seen))

    if alerts:
        for i in range(0, len(alerts), 10):
            chunk = alerts[i : i + 10]
            lines = [
                f'<b>[{html.escape(src)}]</b>\n• <a href="{html.escape(url)}">{html.escape(title)}</a>'
                for src, title, url in chunk
            ]
            send_telegram("<b>New Job Alerts</b>\n\n" + "\n\n".join(lines))
        send_jobs_email(alerts)
        save_seen(seen)


if __name__ == "__main__":
    main()
