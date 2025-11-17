#!/usr/bin/env python3
import os, sys, json, time, re
from datetime import datetime, timezone
from urllib.parse import urlparse
import feedparser

# Optional HTML scraping (off by default to respect ToS/robots).
# If you enable it, install: pip install beautifulsoup4 requests-html
USE_HTML_SCRAPING = False
if USE_HTML_SCRAPING:
    import requests
    from bs4 import BeautifulSoup

CONFIG_PATH = os.environ.get("IS_CONFIG", "config.json")
DATA_OUT = "data/news.json"

def load_config(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def norm(s: str) -> str:
    return (s or "").lower()

def matches_keywords(text: str, keywords: list) -> bool:
    t = norm(text)
    for kw in keywords:
        # Accept simple keywords or quoted phrases
        kw = kw.strip()
        if not kw:
            continue
        if kw.startswith('"') and kw.endswith('"'):
            phrase = kw[1:-1].lower()
            if phrase in t:
                return True
        else:
            # keyword as tokens
            if kw.lower() in t:
                return True
    return False

def fetch_feed(url: str):
    try:
        return feedparser.parse(url)
    except Exception as e:
        print(f"[WARN] feed error {url}: {e}")
        return {"entries": []}

def safe_get(entry, *keys, default=""):
    cur = entry
    for k in keys:
        cur = cur.get(k, {})
    return cur if cur else default

def entry_to_item(entry, source_url: str, keywords: list):
    title = entry.get("title", "")
    summary = entry.get("summary", "") or entry.get("description", "")
    link = entry.get("link", "")
    published = entry.get("published", "") or entry.get("updated", "")
    published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")

    # ISO date fallback
    if published_parsed:
        dt = datetime(*published_parsed[:6], tzinfo=timezone.utc)
        iso = dt.isoformat()
    else:
        iso = ""

    item = {
        "title": title,
        "summary": re.sub("<.*?>", "", summary)[:1000],
        "link": link,
        "source": source_url,
        "published": iso,
        "matched": []
    }

    haystack = f"{title}\n{summary}"
    for kw in keywords:
        if matches_keywords(haystack, [kw]):
            item["matched"].append(kw)

    return item

def scrape_html(url: str):
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "IndustrialStrategyBot/0.1"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # Very naive extraction
        title = soup.title.text.strip() if soup.title else url
        ps = " ".join([p.get_text(" ", strip=True) for p in soup.find_all("p")])[:1500]
        return title, ps
    except Exception as e:
        print(f"[WARN] html scrape fail {url}: {e}")
        return None, None

def main():
    cfg = load_config(CONFIG_PATH)
    keywords = cfg.get("keywords", [])
    sources = cfg.get("rss_sources", [])
    html_sources = cfg.get("html_sources", []) if USE_HTML_SCRAPING else []

    items = []

    for url in sources:
        if not url.strip():
            continue
        feed = fetch_feed(url)
        for entry in feed.get("entries", []):
            item = entry_to_item(entry, url, keywords)
            if item["matched"]:
                items.append(item)

    if USE_HTML_SCRAPING:
        for url in html_sources:
            title, body = scrape_html(url)
            if not title and not body:
                continue
            text = f"{title}\n{body or ''}"
            matched = [kw for kw in keywords if matches_keywords(text, [kw])]
            if matched:
                items.append({
                    "title": title or url,
                    "summary": (body or "")[:1000],
                    "link": url,
                    "source": url,
                    "published": "",
                    "matched": matched
                })

    # sort newest first
    items.sort(key=lambda x: x.get("published") or "", reverse=True)

    os.makedirs("data", exist_ok=True)
    with open(DATA_OUT, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "keywords": keywords,
            "count": len(items),
            "items": items
        }, f, ensure_ascii=False, indent=2)

    print(f"[OK] Wrote {DATA_OUT} with {len(items)} items")

if __name__ == "__main__":
    main()
