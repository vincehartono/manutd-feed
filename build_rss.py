import json, pathlib
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime, format_datetime
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).parent
SETTINGS = json.loads((ROOT / "settings.json").read_text(encoding="utf-8"))

TITLE = SETTINGS.get("title", "My Feed")
LINK = SETTINGS.get("link", "")
DESC = SETTINGS.get("description", "")
MODE = SETTINGS.get("mode", "rss_aggregate")
KEYWORDS = [k.lower() for k in SETTINGS.get("keywords", [])]
EXCLUDE = [k.lower() for k in SETTINGS.get("exclude_keywords", [])]
MAX_ITEMS = int(SETTINGS.get("max_items", 30))
DAYS_LOOKBACK = int(SETTINGS.get("days_lookback", 14))

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

def fetch_rss():
    import feedparser
    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_LOOKBACK)
    for url in SETTINGS.get("rss_sources", []):
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
            items.append({"title": title, "link": link, "guid": guid, "pubDate": dt, "desc": desc})
    # dedupe by guid/link, newest first
    seen = set()
    deduped = []
    for it in sorted(items, key=lambda x: x["pubDate"], reverse=True):
        key = it["guid"] or it["link"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
    return deduped[:MAX_ITEMS]

def fetch_google_sheet():
    import csv, io, requests
    url = (SETTINGS.get("google_sheet_csv_url") or "").strip()
    if not url:
        return []
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    items = []
    reader = csv.DictReader(io.StringIO(r.text))
    for row in reader:
        title = (row.get("title") or "").strip()
        link = (row.get("url") or "").strip()
        desc = (row.get("summary") or "").strip()
        pub  = (row.get("pubDate") or "").strip()
        guid = (row.get("guid") or "").strip() or link
        if not title or not link:
            continue
        dt = norm_pubdate(pub) if pub else datetime.now(timezone.utc)
        if not matches(f"{title}\n{desc}"):
            continue
        items.append({"title": title, "link": link, "guid": guid, "pubDate": dt, "desc": desc})
    items.sort(key=lambda x: x["pubDate"], reverse=True)
    return items[:MAX_ITEMS]

def build_rss(items):
    now_rfc = to_rfc822(datetime.now(timezone.utc))
    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append('<rss version="2.0">')
    out.append('  <channel>')
    out.append('    <title>' + escape(TITLE) + '</title>')
    out.append('    <link>' + escape(LINK) + '</link>')
    out.append('    <description>' + escape(DESC) + '</description>')
    out.append('    <lastBuildDate>' + now_rfc + '</lastBuildDate>')
    for it in items:
        pub = it["pubDate"]
        if isinstance(pub, datetime):
            pub = to_rfc822(pub)
        out.append("    <item>")
        out.append("      <title>" + escape(it["title"]) + "</title>")
        out.append("      <link>" + escape(it["link"]) + "</link>")
        out.append("      <guid isPermaLink=\"false\">" + escape(it["guid"]) + "</guid>")
        out.append("      <pubDate>" + str(pub) + "</pubDate>")
        out.append("      <description><![CDATA[" + it["desc"] + "]]></description>")
        out.append("    </item>")
    out.append("  </channel>")
    out.append("</rss>")
    return "\n".join(out)

def main():
    if MODE == "google_sheet":
        items = fetch_google_sheet()
    else:
        items = fetch_rss()
    outdir = ROOT / "public"
    outdir.mkdir(exist_ok=True, parents=True)
    rss = build_rss(items)
    (outdir / "feed.xml").write_text(rss, encoding="utf-8")
    print(f"Wrote {(outdir / 'feed.xml').as_posix()} with {len(items)} items.")

if __name__ == "__main__":
    main()
