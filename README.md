# Industrial Strategy Tracker (Starter Kit)

This is a tiny skeleton to run a *think-tank-style* tracker for industrial-strategy news and policy updates with **easy updates**.

- **Data ingestion**: `scraper.py` reads `config.json`, fetches RSS/Atom feeds, filters by `keywords`, and writes `data/news.json`.
- **Static site**: `site/index.html` loads `data/news.json` and renders a simple, searchable list (client-side search).
- **Low legal risk**: Uses RSS/Atom feeds rather than raw HTML scraping. You only store titles, links, and short summaries, not full copyrighted articles.

## Quick start

1. Ensure Python 3.10+ and install deps:
   ```bash
   pip install feedparser
   ```

2. Edit `config.json`:
   - Add or remove `keywords`
   - Add your preferred `rss_sources` (government, think tanks, newspapers' RSS if allowed)

3. Run the scraper:
   ```bash
   python scraper.py
   ```
   This writes `data/news.json`.

4. Open the static site:
   - Either open `site/index.html` in your browser, or
   - Serve locally:
     ```bash
     python -m http.server --directory site 8787
     ```
     Then visit http://localhost:8787

## Automate (cron)

On macOS/Linux, run every 2 hours:
```
0 */2 * * * cd /path/to/project && /usr/bin/python3 scraper.py >> logs.txt 2>&1
```

## Optional HTML scraping (advanced)

- Respect robots.txt and site ToS before scraping HTML.
- If permitted, set `USE_HTML_SCRAPING=True` inside `scraper.py` and add `html_sources` in `config.json`.
- Install deps:
  ```bash
  pip install requests beautifulsoup4
  ```

## Deployment options

- **Static hosting**: Netlify, Vercel, GitHub Pages. Just publish `site/` and `data/` contents.
- **CMS route**: Point the domain to WordPress or Ghost; then use RSS importers (WP RSS Aggregator) and your own posts.
- **Search**: This starter uses a simple substring search. For richer search, swap in Fuse.js or Lunr.js.

## Think tank framing (lightweight)

- Add pages in `site/`: `about.html`, `people.html`, `briefs/`.
- Publish 1-page briefs (PDF) summarising major policy docs (linking to originals).
- Add a transparency page (funding, conflicts). Use a CLG (company limited by guarantee) if you want the "think tank" flavour without charity overhead.

## Notes

- Feeds change; keep your `rss_sources` current.
- You can plug this into a newsletter (Buttondown, Beehiiv, Substack) by embedding your sign-up form in `index.html`.
- For a paid tier/API later, you can host `data/news.json` behind a small Flask API and require a token.
