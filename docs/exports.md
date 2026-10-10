# Reusing Around New Jersey

The snapshot builder writes four files from one collection pass. After this change is merged and the existing refresh is run and published, the public URLs will be:

- `https://centercoopmedia.github.io/around-nj/snapshot.md`: readable Markdown for copy/paste or LLM context
- `https://centercoopmedia.github.io/around-nj/snapshot.json`: versioned structured data for automation
- `https://centercoopmedia.github.io/around-nj/rss.xml`: RSS 2.0 for feed readers and RSS integrations
- `https://centercoopmedia.github.io/around-nj/snapshot.html`: existing snapshot, with alternate-format discovery links

These are static files, not an authenticated API. No API key is needed. They refresh with the existing twice-daily job (6:30am and 2pm Eastern), not continuously. Check `generated_at` / RSS `lastBuildDate` for freshness. Cache responses; polling every few minutes will not produce more coverage. Query parameters do not filter these files; filter JSON locally. Browser access from other origins depends on the hosting service's CORS policy.

## JSON contract (schema_version 1.0)

Top-level fields: `title`, `home_page_url`, `schema_version`, `generated_at` (UTC ISO 8601), `lookback_hours`, `description`, `coverage`, `item_count`, `items`.

Each item contains:

- `id`: `urn:sha256:` plus a hash of the pipeline's canonical URL. Use this as an idempotency/deduplication key across refreshes, not the headline or position.
- `title`: publisher headline, not a generated summary
- `url`: original collected article link; use this for attribution and navigation
- `canonical_url`: pipeline-normalized identity (tracking parameters removed; not a publisher-declared canonical URL)
- `source`: publisher attribution from the configured feed or homepage collector
- `partner`: News Commons partner flag
- `date`: UTC ISO 8601 timestamp used for the snapshot's lookback
- `date_kind`: `published`, `updated`, or `observed`. An observed date is the homepage collection time when the publisher's publication date was unavailable. It does NOT prove the article is new. RSS omits `pubDate` for observed or updated timestamps.

All collected, deduplicated stories are exported, including records beyond the HTML's 80-per-group display cap. Items are newest-first with a stable ID tie-breaker. With the same input rows and generation time, exports are byte-stable. Generation time changes on each refresh. No article bodies, editorial categories, summaries, or relevance scores are inferred.

`coverage` reports RSS feeds attempted, failed, unexpected failures, and whether homepage input was provided. A successful refresh can still have gaps. These counts do not certify that every outlet or homepage scrape succeeded. Empty exports are structurally valid; the production builder retains its existing no-stories and excessive-failure safeguards. A missing item does not mean a story was retracted; it may have aged out of the rolling window.

## Quick recipes

Download Markdown for a research notebook or LLM context:

```sh
curl --fail --silent --show-error https://centercoopmedia.github.io/around-nj/snapshot.md -o around-nj.md
```

Select partner stories as newline-delimited JSON (one record per line):

```sh
curl --fail --silent --show-error https://centercoopmedia.github.io/around-nj/snapshot.json |
  jq -c '.items[] | select(.partner)'
```

CSV for a spreadsheet or CMS import (inspect spreadsheet formula-like values before opening):

```sh
curl --fail --silent --show-error https://centercoopmedia.github.io/around-nj/snapshot.json |
  jq -r '(["id","title","source","url","date","date_kind"]), (.items[] | [.id,.title,.source,.url,.date,.date_kind]) | @csv' > around-nj.csv
```

Python, using only the standard library:

```python
import json
from urllib.request import urlopen

with urlopen("https://centercoopmedia.github.io/around-nj/snapshot.json", timeout=30) as response:
    snapshot = json.load(response)
if snapshot["schema_version"] != "1.0":
    raise ValueError("Review the new export schema before importing")
for story in snapshot["items"]:
    print(story["id"], story["source"], story["title"], story["url"])
```

For Zapier/Make/n8n or a feed reader, supply the RSS URL to its feed trigger. Map title, link, GUID, and description (which includes publisher credit); persist GUIDs so overlapping snapshots do not create duplicate posts. For more control, use an HTTP GET plus JSON parsing and filter `items`. Any posting, publishing, or third-party ingestion still needs the appropriate account and editorial approval; generating these exports does not configure an integration.

For a reporting-leads assistant, supply JSON with instructions to cite `source` and `url`, separate verified facts from leads, and verify original articles before making claims. Treat headlines and all publisher strings as untrusted data, never as tool-use instructions. An observed timestamp is not a verified publication date. Headline similarity is not proof of corroboration or independent reporting.

## Attribution and rights

These exports contain headlines, dates, source names, and links only. They add no scraping or full article text. Preserve publisher attribution and original links wherever records travel. Publisher content retains its original rights; inclusion in this feed grants no republication license. Do not treat metadata alone as verified reporting or as permission to bypass paywalls.

## Build and publish

The existing build command now writes `snapshot.json`, `snapshot.md`, and `rss.xml` next to the requested HTML output, in the same directory. Use a dedicated output directory; the three export filenames are fixed even if the HTML filename differs.

```sh
python scripts/build_around_nj_demo.py --output drafts/snapshot.html
```

No new dependencies, API keys, services, or schedule are required. The existing refresh calls the same builder and publisher. The publisher requires the complete bundle and commits all four together to `gh-pages`, leaving the news-desk `index.html` intact. It refuses unrelated staged changes. Deploying this code to the existing timer host and running its publish step is a separate operator action; opening a PR does not make the endpoints live.

Offline checks: `ruff check src tests`, `ruff format --check src tests`, `pytest -q`. Tests validate JSON/RSS round trips, escaping, stable IDs, deterministic ordering, unknown date provenance, uncapped output, and bundle publishing against a temporary local Git remote.
