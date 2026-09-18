# Around New Jersey demo

Public snapshot: https://centercoopmedia.github.io/dnr/

## What it is

NJ PBS asked for a daily, browsable view of what News Commons partners are reporting, not only a morning digest. The page is a 72-hour RSS snapshot built from the Daily News Roundup feed list plus the organizations that signed up on the NJ PBS invitation Airtable.

It uses official NJ PBS marks: the white-and-blue horizontal logo on navy, PBS Sans, and PBS blue for partner labels. Do not use the retired green NJ logo.

## How to use it in a meeting

1. Open https://centercoopmedia.github.io/dnr/
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

The snapshot HTML is generated from Airtable partner coverage plus RSS fetches. Brand assets live on `gh-pages` under `brand/` (logo and PBS Sans). Copy official files from the NJ PBS site brand kit. Do not invent marks.
