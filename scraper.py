#!/usr/bin/env python3
import os
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse  # (kept in case you want it later)
import feedparser

# Optional HTML scraping (off by default to respect ToS/robots).
# If you enable it, install: pip install requests beautifulsoup4
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


def matches_keywords(text: str, keywords: list) -> list:
    """Return list of keywords that match this text."""
    t = norm(text)
    matched = []
    for kw in keywords:
        kw_clean = kw.strip()
        if not kw_clean:
            continue
        if kw_clean.startswith('"') and kw_clean.endswith('"'):
            phrase = kw_clean[1:-1].lower()
            if phrase in t:
                matched.append(kw_clean)
        else:
            if kw_clean.lower() in t:
                matched.append(kw_clean)
    return matched


def fetch_feed(url: str):
    try:
        return feedparser.parse(url)
    except Exception as e:
        print(f"[WARN] feed error {url}: {e}")
        return {"entries": []}


def entry_to_item(entry, source_url: str, keywords: list):
    title = entry.get("title", "") or ""
    summary = entry.get("summary", "") or entry.get("description", "") or ""
    link = entry.get("link", "") or ""
    published = entry.get("published", "") or entry.get("updated", "")
    published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")

    # ISO date fallback
    if published_parsed:
        dt = datetime(*published_parsed[:6], tzinfo=timezone.utc)
        iso = dt.isoformat()
    else:
        iso = ""

    clean_summary = re.sub(r"<.*?>", "", summary)[:1000]

    haystack = f"{title}\n{clean_summary}"
    matched = matches_keywords(haystack, keywords)

    item = {
        "title": title,
        "summary": clean_summary,
        "link": link,
        "source": source_url,
        "published": iso,
        "matched": matched,
    }
    return item


def scrape_html(url: str, keywords: list):
    try:
        r = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "IndustrialStrategyBot/0.1"},
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.text.strip() if soup.title else url
        ps = " ".join(
            [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        )[:1500]
        text = f"{title}\n{ps}"
        matched = matches_keywords(text, keywords)
        return title, ps, matched
    except Exception as e:
        print(f"[WARN] html scrape fail {url}: {e}")
        return None, None, []


def main():
    cfg = load_config(CONFIG_PATH)
    keywords = cfg.get("keywords", [])
    sources = cfg.get("rss_sources", [])
    html_sources = cfg.get("html_sources", []) if USE_HTML_SCRAPING else []

    items = []

    # --- RSS / Atom feeds ---
    for url in sources:
        url = (url or "").strip()
        if not url:
            continue
        feed = fetch_feed(url)
        for entry in feed.get("entries", []):
            item = entry_to_item(entry, url, keywords)
            # Always include the item; "matched" is just metadata
            items.append(item)

    # --- Optional HTML scraping (off by default) ---
    if USE_HTML_SCRAPING:
        for url in html_sources:
            url = (url or "").strip()
            if not url:
                continue
            title, body, matched = scrape_html(url, keywords)
            if not title and not body:
                continue
            items.append({
                "title": title or url,
                "summary": (body or "")[:1000],
                "link": url,
                "source": url,
                "published": "",
                "matched": matched,
            })

    # Sort newest first (blank published dates go last)
    items.sort(key=lambda x: x.get("published") or "", reverse=True)

    os.makedirs("data", exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "keywords": keywords,
        "count": len(items),
        "items": items,
    }

    with open(DATA_OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[OK] Wrote {DATA_OUT} with {len(items)} items")


if __name__ == "__main__":
    main()
