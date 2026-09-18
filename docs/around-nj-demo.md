# Around New Jersey demo

Public snapshot: https://centercoopmedia.github.io/around-nj/

## What it is

NJ PBS asked for a daily, browsable view of what News Commons partners are reporting, not only a morning digest. The page is a 72-hour RSS snapshot built from the Daily News Roundup feed list plus the organizations that signed up on the NJ PBS invitation Airtable.

It uses official NJ PBS marks: the white-and-blue horizontal logo on navy, PBS Sans, and PBS blue for partner labels. Do not use the retired green NJ logo.

## How to use it in a meeting

1. Open https://centercoopmedia.github.io/around-nj/
2. Show partner headlines first.
3. Switch to All stories for the statewide layer (Village Green, Morristown Green, and the rest of the DNR list).
4. Use Partners only to hide everything except the invitation-list outlets.

## Limits

- Snapshot, not a live all-day product.
- No paywall login. No Mailchimp send.
- TAPinto RSS returns HTTP 403 on the town feeds in `config/rss_feeds.json`.
- Several USA Today network feeds in that file return 404.
- GitHub Pages is the `gh-pages` branch. Application code stays on `master`.

## Firecrawl fallbacks

Some invitation-list outlets have no RSS, a JavaScript homepage, or a blocked feed (TAPinto 403). Those rows can set `"scrape": "https://..."`. The refresh job uses Firecrawl to extract recent headlines from the homepage and merges them into the snapshot.

Skip Facebook pages, scanners, and outlets with no public homepage for now. Firecrawl is authenticated on officejawn via `FIRECRAWL_API_KEY` / `pass claude/api/firecrawl`.

```bash
python scripts/scrape_partner_homepages.py --output drafts/scraped_headlines.json
python scripts/build_around_nj_demo.py \
  --scraped-json drafts/scraped_headlines.json \
  --output drafts/snapshot.html
```

Twice-daily timer (6:30am and 2:00pm Eastern): `deploy/systemd/around-nj-refresh.timer`. It builds locally and publishes `snapshot.html` to the `gh-pages` worktree at `$AROUND_NJ_PAGES` (default `/home/jamditis/projects/around-nj-live`). Do not overwrite `index.html`; that file is the news desk.

Publish commits include `[skip ci]`. The Playwright “News desk checks” workflow is disabled until NJ PBS owns GitHub Actions minutes. Pre-merge CI on `master` (ruff, pytest, gitleaks, `CI gate`) stays on. GitHub Pages still has to run its own static deploy so the public URL updates.

## Rebuild

From the repository, with `feedparser` and `requests` installed:

```bash
python scripts/build_around_nj_demo.py --output drafts/around-nj-demo.html
```

That command reads `config/rss_feeds.json` and `config/pbs_partners.json`, fetches the last 72 hours, and writes branded HTML. It does not need Airtable keys.

Publish to GitHub Pages from a `gh-pages` checkout that already has `brand/` (official NJ PBS logo and PBS Sans):

```bash
cp drafts/snapshot.html /path/to/gh-pages/snapshot.html
git -C /path/to/gh-pages add snapshot.html
git -C /path/to/gh-pages commit -m "Refresh Around New Jersey snapshot."
git -C /path/to/gh-pages push origin gh-pages
```

Copy official brand files from the NJ PBS site brand kit into `gh-pages/brand/`. Do not invent marks.
