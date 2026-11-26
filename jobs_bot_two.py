import json
import os
import smtplib
from email.mime.text import MIMEText
import requests

BOT_TOKEN = os.environ["BOT_TOKEN_TWO"]
CHAT_ID = os.environ["CHAT_ID_TWO"]
EMAIL_USER = os.environ.get("EMAIL_USER", "")
EMAIL_PASS = os.environ.get("EMAIL_PASS", "")
EMAIL_TO = "nc.nothingphone@gmail.com"

BOARDS_FILE = "boards_two.json"
SEEN_FILE = "seen_jobs_two.json"

TITLE_INCLUDE = [
    "ai ", " ai", "ml ", " ml", "machine learning", "llm", "agent",
    "software engineer", "swe", "full stack", "fullstack", "backend",
    "product engineer", "founding engineer", "forward deployed",
    "solutions engineer", "member of technical staff", "mts", "python",
    "typescript", "voice", "applied ai", "generative ai",
]

TITLE_EXCLUDE = [
    "senior", "sr.", "sr ", "staff", "principal", "lead", "manager",
    "director", "head of", "vp", "architect", "recruiter", "sales",
    "marketing", "account executive", "counsel", "finance", "hr ",
    "intern", "internship",
]

LOCATION_INCLUDE = [
    "india", "bengaluru", "bangalore", "hyderabad", "delhi", "ncr",
    "gurgaon", "gurugram", "noida", "pune", "mumbai", "chennai",
    "remote", "apac", "global", "anywhere", "distributed", "worldwide",
]


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def matches_filters(title, location, is_remote=False):
    t = f" {title.lower()} "
    if any(bad in t for bad in TITLE_EXCLUDE):
        return False
    if not any(good in t for good in TITLE_INCLUDE):
        return False
    loc = (location or "").lower().strip()
    if is_remote or not loc:
        return True
    return any(k in loc for k in LOCATION_INCLUDE)


def fetch_workable(slug):
    jobs = []
    try:
        r = requests.get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}", timeout=15)
        if r.status_code != 200:
            return jobs
        for j in r.json().get("jobs", []):
            title = j.get("title", "")
            loc = ", ".join(filter(None, [j.get("city", ""), j.get("country", "")]))
            is_remote = bool(j.get("telecommuting", False))
            url = j.get("url", "")
            if url and matches_filters(title, loc, is_remote):
                jobs.append({"id": f"wk:{slug}:{j.get('shortcode', url)}", "company": slug, "title": title, "location": loc or ("Remote" if is_remote else "Unspecified"), "url": url, "ats": "Workable"})
    except Exception:
        pass
    return jobs


def fetch_smartrecruiters(slug):
    jobs = []
    try:
        r = requests.get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", params={"limit": 100}, timeout=15)
        if r.status_code != 200:
            return jobs
        for j in r.json().get("content", []):
            title = j.get("name", "")
            loc_obj = j.get("location", {}) or {}
            loc = ", ".join(filter(None, [loc_obj.get("city", ""), loc_obj.get("country", "")]))
            is_remote = bool(loc_obj.get("remote", False))
            job_id = j.get("id", "")
            url = f"https://jobs.smartrecruiters.com/{slug}/{job_id}"
            if job_id and matches_filters(title, loc, is_remote):
                jobs.append({"id": f"sr:{slug}:{job_id}", "company": slug, "title": title, "location": loc or ("Remote" if is_remote else "Unspecified"), "url": url, "ats": "SmartRecruiters"})
    except Exception:
        pass
    return jobs


def fetch_rippling(slug):
    jobs = []
    try:
        r = requests.get(f"https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs", timeout=15)
        if r.status_code != 200:
            return jobs
        data = r.json()
        items = data if isinstance(data, list) else data.get("jobs", [])
        for j in items:
            title = j.get("name", "")
            loc_obj = j.get("workLocation", {}) or {}
            loc = loc_obj.get("label", "") if isinstance(loc_obj, dict) else str(loc_obj)
            url = j.get("url", "")
            uid = j.get("uuid", url)
            if url and matches_filters(title, loc, "remote" in loc.lower()):
                jobs.append({"id": f"rp:{slug}:{uid}", "company": slug, "title": title, "location": loc or "Unspecified", "url": url, "ats": "Rippling"})
    except Exception:
        pass
    return jobs


def send_telegram(new_jobs):
    chunk = []
    for j in new_jobs:
        line = f"<b>{j['title']}</b>\n{j['company']} ({j['ats']}) | {j['location']}\n{j['url']}"
        chunk.append(line)
        if len(chunk) == 8:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": CHAT_ID, "text": "\n\n".join(chunk), "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=15,
            )
            chunk = []
    if chunk:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": "\n\n".join(chunk), "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=15,
        )


def send_email(new_jobs):
    if not EMAIL_USER or not EMAIL_PASS:
        return
    body_lines = [f"{j['title']} - {j['company']} ({j['ats']}) [{j['location']}]\n{j['url']}" for j in new_jobs]
    msg = MIMEText("\n\n".join(body_lines), "plain", "utf-8")
    msg["Subject"] = f"[Job Alert Bot 2] {len(new_jobs)} New Listings"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())


def main():
    boards = load_json(BOARDS_FILE, {"workable": [], "smartrecruiters": [], "rippling": []})
    seen = set(load_json(SEEN_FILE, []))
    found = []

    for slug in boards.get("workable", []):
        found.extend(fetch_workable(slug))
    for slug in boards.get("smartrecruiters", []):
        found.extend(fetch_smartrecruiters(slug))
    for slug in boards.get("rippling", []):
        found.extend(fetch_rippling(slug))

    new_jobs = [j for j in found if j["id"] not in seen]
    print(f"Total matched: {len(found)} | New: {len(new_jobs)}")

    if new_jobs:
        send_telegram(new_jobs)
        send_email(new_jobs)
        for j in new_jobs:
            seen.add(j["id"])
        save_json(SEEN_FILE, sorted(seen))


if __name__ == "__main__":
    main()
