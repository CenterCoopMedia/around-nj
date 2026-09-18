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

## Rebuild

From the repository, with `feedparser` and `requests` installed:

```bash
python scripts/build_around_nj_demo.py --output drafts/around-nj-demo.html
```

That command reads `config/rss_feeds.json` and `config/pbs_partners.json`, fetches the last 72 hours, and writes branded HTML. It does not need Airtable keys.

Publish to GitHub Pages from a `gh-pages` checkout that already has `brand/` (official NJ PBS logo and PBS Sans):

```bash
cp drafts/around-nj-demo.html /path/to/gh-pages/index.html
git -C /path/to/gh-pages add index.html
git -C /path/to/gh-pages commit -m "Refresh Around New Jersey snapshot."
git -C /path/to/gh-pages push origin gh-pages
```

Copy official brand files from the NJ PBS site brand kit into `gh-pages/brand/`. Do not invent marks.
