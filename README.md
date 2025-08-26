# Man Utd Auto Feed (RSS Aggregator / Google Sheet)

This template can **automatically add posts** to your RSS feed in two ways:
1) **rss_aggregate** — pull from multiple RSS sources, filter by keywords, dedupe.
2) **google_sheet** — read a published-to-web Google Sheet CSV you edit.

The GitHub Action runs on a schedule and deploys `public/feed.xml` to GitHub Pages.

## Quick setup
1. Upload these files to a GitHub repo.
2. In `settings.json`, pick `"mode"` and fill in sources (RSS or Google Sheet CSV).
3. Ensure **Settings → Pages → Source = GitHub Actions**.
4. Push a commit or **Run workflow**. Your feed URL:
   `https://<YOUR_USER>.github.io/<REPO_NAME>/feed.xml`

---
Generated 2025-08-26T20:19:16.399861Z
