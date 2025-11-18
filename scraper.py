#!/usr/bin/env python3
import os
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse  # kept in case you want it later
import feedparser

# Optional HTML scraping (off by default to respect ToS/robots).
# If you enable it, install: pip install requests beautifulsoup4
USE_HTML_SCRAPING = False
if USE_HTML_SCRAPING:
    import requests
    from bs4 import BeautifulSoup

CONFIG_PATH = os.environ.get("IS_CONFIG", "config.json")
DATA_OUT = "data/news.json"

# Try to load transformers for AI summaries
try:
    from transformers import pipeline
    HAVE_TRANSFORMERS = True
except ImportError:
    HAVE_TRANSFORMERS = False

_SUMMARIZER = None


def get_summarizer():
    """Lazy init for the summariser pipeline."""
    global _SUMMARIZER
    if not HAVE_TRANSFORMERS:
        return None
    if _SUMMARIZER is None:
        # Small-ish summarisation model, fine on CPU in Actions
        _SUMMARIZER = pipeline(
            "summarization",
            model="sshleifer/distilbart-cnn-12-6",
        )
    return _SUMMARIZER


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
        # Will fill these later if transformers is available
        "ai_summary": "",
        "ai_tags": [],
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


def xml_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;") \
                    .replace("<", "&lt;") \
                    .replace(">", "&gt;") \
                    .replace('"', "&quot;")


def infer_ai_tags(text: str) -> list:
    """
    Cheap tag inference on top of the keyword logic.
    No heavy model here, just heuristics.
    """
    t = text.lower()
    tags = set()

    def add_if(substr, label):
        if substr in t:
            tags.add(label)

    add_if("hydrogen", "Hydrogen")
    add_if("fuel cell", "Fuel cells")
    add_if("net zero", "Net zero")
    add_if("decarbonis", "Decarbonisation")
    add_if("industrial strategy", "Industrial strategy")
    add_if("manufactur", "Manufacturing")
    add_if("supply chain", "Supply chains")
    add_if("semiconductor", "Semiconductors")
    add_if("chips act", "CHIPS / semiconductors")
    add_if("ira ", "US IRA")
    add_if("r&d", "R&D")
    add_if("research and development", "R&D")
    add_if("innovation", "Innovation")
    add_if("clean energy", "Clean energy")
    add_if("heat pump", "Heat pumps")
    add_if("nuclear", "Nuclear")
    add_if("small modular reactor", "SMRs")
    add_if("trade", "Trade")
    add_if("export", "Trade")

    return sorted(tags)


def add_ai_fields(items: list):
    """
    Add ai_summary and ai_tags for each item if transformers is available.
    To keep runtime sensible we cap the number of items we summarise.
    """
    summariser = get_summarizer()
    if summariser is None:
        print("[INFO] transformers not available, skipping AI summaries.")
        # Still add heuristic tags
        for item in items:
            text = f"{item.get('title','')} {item.get('summary','')}"
            item["ai_tags"] = infer_ai_tags(text)
        return

    max_items = 50  # summarise only the most recent 50 to keep things light
    for idx, item in enumerate(items):
        text = f"{item.get('title','')}. {item.get('summary','')}".strip()
        text = text.replace("\n", " ")
        if not text or len(text) < 40:
            item["ai_summary"] = ""
        else:
            try:
                # keep input short for speed
                input_text = text[:900]
                out = summariser(
                    input_text,
                    max_length=50,
                    min_length=8,
                    do_sample=False,
                )
                summary_text = out[0]["summary_text"].strip()
                item["ai_summary"] = summary_text
            except Exception as e:
                print(f"[WARN] summarisation failed for item {idx}: {e}")
                item["ai_summary"] = ""

        # heuristic tags on top
        text_for_tags = f"{item.get('title','')} {item.get('summary','')}"
        item["ai_tags"] = infer_ai_tags(text_for_tags)

        if idx + 1 >= max_items:
            # For older items, just tags, no summaries
            break

    # For remaining items (beyond max_items), at least add tags
    for item in items[max_items:]:
        text_for_tags = f"{item.get('title','')} {item.get('summary','')}"
        item["ai_tags"] = infer_ai_tags(text_for_tags)


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
            text = (body or "")[:1000]
            items.append({
                "title": title or url,
                "summary": text,
                "link": url,
                "source": url,
                "published": "",
                "matched": matched,
                "ai_summary": "",
                "ai_tags": [],
            })

    # Sort newest first (blank published dates go last)
    items.sort(key=lambda x: x.get("published") or "", reverse=True)

    # Add AI enrichments
    add_ai_fields(items)

    os.makedirs("data", exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    payload = {
        "generated_at": generated_at,
        "keywords": keywords,
        "count": len(items),
        "items": items,
    }

    # Write JSON for the web app
    with open(DATA_OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # Also write a simple RSS feed (top 50 items)
    rss_items = []
    for item in items[:50]:
        title = xml_escape(item.get("title", ""))
        link = xml_escape(item.get("link", ""))
        description = xml_escape(
            item.get("ai_summary") or item.get("summary") or ""
        )
        pubdate = item.get("published") or generated_at
        rss_items.append(
            f"""
    <item>
      <title>{title}</title>
      <link>{link}</link>
      <description>{description}</description>
      <pubDate>{xml_escape(pubdate)}</pubDate>
    </item>"""
        )

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Industrial Strategy Tracker</title>
    <link>https://industrialstrategy.github.io/industrialstrategy/</link>
    <description>Updates from government and industry sources.</description>
    <lastBuildDate>{xml_escape(generated_at)}</lastBuildDate>
    {''.join(rss_items)}
  </channel>
</rss>
"""

    with open("data/feed.xml", "w", encoding="utf-8") as f_rss:
        f_rss.write(rss)

    print(f"[OK] Wrote {DATA_OUT} with {len(items)} items and data/feed.xml")


if __name__ == "__main__":
    main()
