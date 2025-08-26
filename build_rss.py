#!/usr/bin/env python3
"""
Builds an RSS feed at public/feed.xml and summary pages at public/posts/*.html.

Config: settings.json
{
  "title": "United Pulse",
  "link": "https://manchesterunitednews.godaddysites.com/",
  "description": "Live Manchester United updates (auto-aggregated).",
  "mode": "rss_aggregate",        // or "google_sheet"
  "rss_sources": ["https://.../feed", "..."],
  "google_sheet_csv_url": "https://docs.google.com/.../pub?output=csv",
  "keywords": ["Manchester United", "Man Utd", "MUFC"],
  "exclude_keywords": [],
  "max_items": 40,
  "days_lookback": 14,
  "site_base": "https://vincehartono.github.io/manutd-feed"  // NO trailing slash
}
"""
import csv
import io
import json
import pathlib
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime, format_datetime
from typing import Dict, List
from xml.sax.saxutils import escape
import requests
from bs4 import BeautifulSoup

# ---------- load settings ----------
ROOT = pathlib.Path(__file__).parent
SETTINGS = json.loads((ROOT / "settings.json").read_text(encoding="utf-8"))

TITLE: str = SETTINGS.get("title", "My Feed")
LINK: str = SETTINGS.get("link", "")
DESC: str = SETTINGS.get("description", "")
MODE: str = SETTINGS.get("mode", "rss_aggregate")
KEYWORDS = [k.lower() for k in SETTINGS.get("keywords", [])]
EXCLUDE = [k.lower() for k in SETTINGS.get("exclude_keywords", [])]
MAX_ITEMS: int = int(SETTINGS.get("max_items", 30))
DAYS_LOOKBACK: int = int(SETTINGS.get("days_lookback", 14))
SITE_BASE: str = SETTINGS.get("site_base", "").rstrip("/")

RSS_SOURCES: List[str] = SETTINGS.get("rss_sources", [])
GOOGLE_SHEET_CSV_URL: str = SETTINGS.get("google_sheet_csv_url", "")

# ---------- helpers ----------
def to_rfc822(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt)

def norm_pubdate(dt_str: str) -> datetime:
    try:
        dt = parsedate_to_datetime(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)

def matches(text: str) -> bool:
    t = (text or "").lower()
    if KEYWORDS and not any(k in t for k in KEYWORDS):
        return False
    if EXCLUDE and any(x in t for x in EXCLUDE):
        return False
    return True

_SLUG_RE = re.compile(r"[^a-z0-9]+")
def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = _SLUG_RE.sub("-", s).strip("-")
    return s[:80] or "post"

def dedupe_and_sort(items: List[Dict]) -> List[Dict]:
    # newest first, dedupe by guid (or link)
    seen = set()
    out = []
    for it in sorted(items, key=lambda x: x["pubDate"], reverse=True):
        key = it.get("guid") or it.get("link")
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out[:MAX_ITEMS]

# ---------- fetchers ----------
def fetch_rss() -> List[Dict]:
    import feedparser
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_LOOKBACK)
    items: List[Dict] = []
    for url in RSS_SOURCES:
        url = (url or "").strip()
        if not url:
            continue
        feed = feedparser.parse(url)
        for e in feed.entries:
            title = getattr(e, "title", "").strip()
            link = getattr(e, "link", "").strip()
            desc = getattr(e, "summary", "").strip() or getattr(e, "description", "").strip()
            guid = getattr(e, "id", "") or link
            pub = getattr(e, "published", "") or getattr(e, "updated", "")
            dt = norm_pubdate(pub) if pub else datetime.now(timezone.utc)
            if dt < cutoff:
                continue
            if not matches(f"{title}\n{desc}"):
                continue
            items.append({
                "title": title,
                "link": link,              # original link
                "guid": guid,              # keep guid as original for stable dedupe
                "pubDate": dt,
                "desc": desc
            })
    return dedupe_and_sort(items)

def fetch_google_sheet() -> List[Dict]:
    import requests
    if not GOOGLE_SHEET_CSV_URL:
        return []
    r = requests.get(GOOGLE_SHEET_CSV_URL, timeout=30)
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    items: List[Dict] = []
    for row in reader:
        title = (row.get("title") or "").strip()
        link = (row.get("url") or "").strip()
        desc = (row.get("summary") or "").strip()
        pub = (row.get("pubDate") or "").strip()
        guid = (row.get("guid") or "").strip() or link
        if not title or not link:
            continue
        dt = norm_pubdate(pub) if pub else datetime.now(timezone.utc)
        if not matches(f"{title}\n{desc}"):
            continue
        items.append({
            "title": title,
            "link": link,              # original link you provided
            "guid": guid,
            "pubDate": dt,
            "desc": desc
        })
    return dedupe_and_sort(items)

# ---------- summary pages ----------
SUMMARY_CSS = """
:root{--fg:#111;--muted:#666;--bg:#fff;--acc:#cc0000}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,"Helvetica Neue",Arial}
main{max-width:820px;margin:3rem auto;padding:0 1rem}
h1{font-size:1.9rem;margin:0 0 0.5rem}
p{margin:1rem 0}
a{color:var(--acc);text-decoration:none}
a:hover{text-decoration:underline}
.card{border:1px solid #eee;border-radius:14px;padding:1rem 1.2rem;margin:1rem 0;box-shadow:0 1px 2px rgba(0,0,0,.03)}
.meta{color:var(--muted);font-size:.95rem}
.btn{display:inline-block;margin-top:1rem;border:1px solid var(--acc);padding:.5rem .9rem;border-radius:10px}
footer{margin:3rem 0 1rem;color:var(--muted);font-size:.9rem}
"""

def render_summary_html(title: str, original_url: str, desc: str, pub_dt: datetime) -> str:
    pub_str = to_rfc822(pub_dt)
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="canonical" href="{escape(original_url)}">
<title>{escape(title)}</title>
<style>{SUMMARY_CSS}</style>
<main>
  <article class="card">
    <h1>{escape(title)}</h1>
    <div class="meta">Published: {escape(pub_str)}</div>
    <p>{desc}</p>
    <p><a class="btn" href="{escape(original_url)}" rel="noopener nofollow">Read the original article →</a></p>
  </article>
  <footer>Curated by <a href="{escape(LINK)}">{escape(TITLE)}</a></footer>
</main>
</html>"""

def write_summary_pages(items: List[Dict]) -> None:
    posts_dir = ROOT / "public" / "posts"
    posts_dir.mkdir(parents=True, exist_ok=True)
    article_base = SETTINGS.get("article_page_base", "").rstrip("/")
    for it in items:
        slug = slugify(it["title"] or it["guid"])
        it["slug"] = slug

        # Build the GitHub summary page (no redirect)
        html = render_summary_html(it["title"], it["link"], it["desc"], it["pubDate"])
        (posts_dir / f"{slug}.html").write_text(html, encoding="utf-8")

        # Tell the RSS to use your GoDaddy page if configured, else GitHub pages
        if article_base:
            it["summary_url"] = f"{article_base}#slug={slug}"
        elif SITE_BASE:
            it["summary_url"] = f"{SITE_BASE}/posts/{slug}.html"
        else:
            it["summary_url"] = it["link"]


def write_index(items: List[Dict]) -> None:
    # simple landing page with links to summaries
    lines = [
        "<!doctype html><meta charset='utf-8'><title>{}</title>".format(escape(TITLE)),
        "<style>body{font:16px/1.6 system-ui;margin:2rem} a{color:#cc0000;text-decoration:none} a:hover{text-decoration:underline}</style>",
        f"<h1>{escape(TITLE)}</h1>",
        f"<p>{escape(DESC)}</p>",
        "<ul>"
    ]
    for it in items:
        link = it.get("summary_url") or it.get("link")
        lines.append(f"<li><a href='{escape(link)}'>{escape(it['title'])}</a></li>")
    lines.append("</ul>")
    (ROOT / "public" / "index.html").write_text("\n".join(lines), encoding="utf-8")

# ---------- RSS output ----------
def build_rss(items: List[Dict]) -> str:
    now_rfc = to_rfc822(datetime.now(timezone.utc))
    parts = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append('<rss version="2.0">')
    parts.append('  <channel>')
    parts.append('    <title>' + escape(TITLE) + '</title>')
    parts.append('    <link>' + escape(LINK) + '</link>')
    parts.append('    <description>' + escape(DESC) + '</description>')
    parts.append('    <lastBuildDate>' + now_rfc + '</lastBuildDate>')
    for it in items:
        # Link to the summary page (preferred), keep guid as original for stable dedupe
        link_for_rss = it.get("summary_url") or it["link"]
        pub = it["pubDate"]
        if isinstance(pub, datetime):
            pub = to_rfc822(pub)
        # include original link inside description
        desc_with_link = f"""{it['desc']}<br/><br/>
<a href="{escape(it['link'])}" rel="noopener nofollow">Read original →</a>"""
        parts.append("    <item>")
        parts.append("      <title>" + escape(it["title"]) + "</title>")
        parts.append("      <link>" + escape(link_for_rss) + "</link>")
        parts.append('      <guid isPermaLink="true">' + escape(link_for_rss) + "</guid>")
        parts.append("      <pubDate>" + str(pub) + "</pubDate>")
        parts.append("      <description><![CDATA[" + desc_with_link + "]]></description>")
        parts.append("    </item>")
    parts.append("  </channel>")
    parts.append("</rss>")
    return "\n".join(parts)

def enrich_summary(original_url: str, desc: str) -> str:
    """Fetch the article and build a longer summary (meta description + first paragraphs)."""
    desc = (desc or "").strip()
    # If we already have a reasonably long summary, keep it
    if len(desc) >= 500:
        return desc
    try:
        r = requests.get(original_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # meta descriptions
        best = ""
        og = soup.find("meta", attrs={"property": "og:description"})
        if og and og.get("content"):
            best = og["content"].strip()
        if not best:
            md = soup.find("meta", attrs={"name": "description"})
            if md and md.get("content"):
                best = md["content"].strip()

        # first few paragraphs inside <article> or <main>
        container = soup.find("article") or soup.find("main") or soup
        paras = []
        for p in container.find_all("p", limit=6):
            txt = p.get_text(" ", strip=True)
            if len(txt) > 60:
                paras.append(txt)
            if sum(len(x) for x in paras) > 900:
                break

        # pick the longest between existing desc, meta, and paragraphs
        cand = max([desc, best, " ".join(paras)], key=lambda s: len(s or ""))
        cand = (cand[:1200] + "…") if len(cand) > 1200 else cand
        return cand or desc
    except Exception:
        return desc

# ---------- main ----------
def main():
    if MODE == "google_sheet":
        items = fetch_google_sheet()
    else:
        items = fetch_rss()

    outdir = ROOT / "public"
    outdir.mkdir(parents=True, exist_ok=True)

    # 1) Enrich summaries (loop)
    for it in items:
        it["desc"] = enrich_summary(it["link"], it["desc"])

    # 2) Build pages once (not inside the loop)
    write_summary_pages(items)
    write_index(items)

    # 3) Write feed
    rss_xml = build_rss(items)
    (outdir / "feed.xml").write_text(rss_xml, encoding="utf-8")
    print(f"Wrote {(outdir / 'feed.xml').as_posix()} with {len(items)} item(s).")

if __name__ == "__main__":
    main()
