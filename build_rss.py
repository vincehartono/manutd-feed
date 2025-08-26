from datetime import datetime
from email.utils import format_datetime
from xml.sax.saxutils import escape
import csv, pathlib, json

ROOT = pathlib.Path(__file__).parent
SETTINGS = json.loads((ROOT / "settings.json").read_text(encoding="utf-8"))

SITE_TITLE = SETTINGS.get("title", "My Feed")
SITE_LINK = SETTINGS.get("link", "")
SITE_DESC = SETTINGS.get("description", "")

def build_items(csv_path: pathlib.Path):
    items = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            title = (row.get("title") or "").strip()
            link = (row.get("url") or "").strip()
            desc = (row.get("summary") or "").strip()
            pub = (row.get("pubDate") or "").strip() or format_datetime(datetime.utcnow())
            guid = (row.get("guid") or "").strip() or link
            if not title or not link:
                continue
            items.append({
                "title": title,
                "link": link,
                "guid": guid,
                "pubDate": pub,
                "desc": desc
            })
    items.sort(key=lambda x: x["pubDate"], reverse=True)
    return items

def build_rss(items):
    now_rfc = format_datetime(datetime.utcnow())
    rss_head = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n'
        '  <channel>\n'
        '    <title>' + escape(SITE_TITLE) + '</title>\n'
        '    <link>' + escape(SITE_LINK) + '</link>\n'
        '    <description>' + escape(SITE_DESC) + '</description>\n'
        '    <lastBuildDate>' + now_rfc + '</lastBuildDate>\n'
    )
    rss_items = []
    for it in items:
        rss_items.append(
            "    <item>\n"
            "      <title>" + escape(it['title']) + "</title>\n"
            "      <link>" + escape(it['link']) + "</link>\n"
            "      <guid isPermaLink=\"false\">" + escape(it['guid']) + "</guid>\n"
            "      <pubDate>" + escape(it['pubDate']) + "</pubDate>\n"
            "      <description><![CDATA[" + it['desc'] + "]]></description>\n"
            "    </item>\n"
        )
    rss_tail = "  </channel>\n</rss>\n"
    return rss_head + "".join(rss_items) + rss_tail

def main():
    items = build_items(ROOT / "posts.csv")
    outdir = ROOT / "public"
    outdir.mkdir(exist_ok=True, parents=True)
    rss = build_rss(items)
    (outdir / "feed.xml").write_text(rss, encoding="utf-8")
    print(f"Wrote {(outdir / 'feed.xml').as_posix()} with {len(items)} item(s).")

if __name__ == "__main__":
    main()
