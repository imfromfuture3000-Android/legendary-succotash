#!/usr/bin/env python3
"""
OMEGA-PRIME Agent
-----------------
Zero-cost crypto scout:
- Scans RSS feeds (airdrops, testnets, quests, dev blogs, Nitter/Twitter)
- Scores opportunities
- Saves to SQLite + CSV
- (Optional) sends alerts to Telegram / Discord
"""

import os, json, time, hashlib, sqlite3, csv, requests, feedparser
from datetime import datetime

# -----------------------
# Load Config
# -----------------------
with open("omega.config.json", "r") as f:
    CONFIG = json.load(f)

DB_PATH = CONFIG.get("db_path", "omega.db")
CSV_PATH = CONFIG.get("csv_path", "opportunities.csv")
POLL_MINUTES = CONFIG.get("poll_minutes", 10)
FEEDS = CONFIG.get("rss_feeds", [])
NOTIFY = CONFIG.get("notify", {})

# -----------------------
# Init SQLite DB
# -----------------------
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    source TEXT,
    title TEXT,
    url TEXT,
    published TEXT,
    summary TEXT,
    score INTEGER,
    reason TEXT,
    tags TEXT,
    fetched_at TEXT
)
""")
conn.commit()

# -----------------------
# Utility Functions
# -----------------------
def hash_id(source, url):
    return hashlib.sha256((source + url).encode()).hexdigest()

def score_item(title, summary):
    """Basic keyword scoring system"""
    text = (title + " " + summary).lower()
    score, tags, reasons = 0, [], []

    keywords = {
        "airdrop": 5,
        "testnet": 4,
        "quest": 3,
        "reward": 2,
        "bounty": 4,
        "grant": 2,
        "retrodrop": 5,
        "campaign": 2,
        "earn": 1
    }

    for word, val in keywords.items():
        if word in text:
            score += val
            tags.append(word)
            reasons.append(f"{word}+{val}")

    return score, tags, ";".join(reasons)

def save_to_db(item):
    cur.execute("""
    INSERT OR IGNORE INTO opportunities
    (id, source, title, url, published, summary, score, reason, tags, fetched_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item["id"], item["source"], item["title"], item["url"],
        item["published"], item["summary"], item["score"], item["reason"],
        ",".join(item["tags"]), item["fetched_at"]
    ))
    conn.commit()

def save_to_csv(item):
    exists = os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not exists:  # write header if new file
            writer.writerow(["id","source","title","url","published","summary","score","reason","tags","fetched_at"])
        writer.writerow([
            item["id"], item["source"], item["title"], item["url"],
            item["published"], item["summary"], item["score"], item["reason"],
            ",".join(item["tags"]), item["fetched_at"]
        ])

def notify(item):
    text = f"💡 New Opportunity: {item['title']}\n{item['url']}\nScore: {item['score']} | Tags: {','.join(item['tags'])}"

    # Telegram
    if NOTIFY.get("telegram", {}).get("enabled"):
        token = os.getenv("TG_BOT_TOKEN", NOTIFY["telegram"].get("bot_token"))
        chat_id = os.getenv("TG_CHAT_ID", NOTIFY["telegram"].get("chat_id"))
        if token and chat_id:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": text}
            )

    # Discord
    if NOTIFY.get("discord", {}).get("enabled"):
        webhook = os.getenv("DISCORD_WEBHOOK_URL", NOTIFY["discord"].get("webhook_url"))
        if webhook:
            requests.post(webhook, json={"content": text})

# -----------------------
# Main Loop
# -----------------------
def fetch_feed(url):
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            uid = hash_id(url, entry.get("link", ""))
            cur.execute("SELECT id FROM opportunities WHERE id=?", (uid,))
            if cur.fetchone():
                continue  # already stored

            title = entry.get("title", "").strip()
            summary = entry.get("summary", "").strip()
            link = entry.get("link", "")
            published = entry.get("published", "")

            score, tags, reason = score_item(title, summary)
            item = {
                "id": uid,
                "source": url,
                "title": title,
                "url": link,
                "published": published,
                "summary": summary,
                "score": score,
                "reason": reason,
                "tags": tags,
                "fetched_at": datetime.utcnow().isoformat()
            }

            save_to_db(item)
            save_to_csv(item)

            if score >= 3:  # only notify for relevant ones
                notify(item)

            print(f"[+] {title} ({tags}) -> Score {score}")

    except Exception as e:
        print(f"[!] Error fetching {url}: {e}")

def run_once():
    print(f"\n=== OMEGA-PRIME run {datetime.utcnow().isoformat()} ===")
    for url in FEEDS:
        fetch_feed(url)

if __name__ == "__main__":
    run_once()  # one-shot for GitHub Actions
    # For local continuous run:
    # while True:
    #     run_once()
    #     time.sleep(POLL_MINUTES * 60)
