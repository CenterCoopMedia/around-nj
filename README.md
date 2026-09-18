# Around New Jersey news desk

Static NJ PBS headline browser for the Daily News Roundup demo. This branch is GitHub Pages only. Application code stays on `master`.

## Preview

From this branch, run `python -m http.server 8000` and open `http://localhost:8000`. The desk uses native JavaScript modules and one same-origin fetch. Opening `index.html` directly as a file will not load the index; `snapshot.html` remains a plain reading page.

## Files and publishing

- `index.html`: accessible page shell, controls, and explanations.
- `assets/desk.css`: responsive PBS-branded light/dark layouts and print styles.
- `assets/desk.mjs`: browser interactions, local bookmarks, URL state, and rendering.
- `assets/desk-core.mjs`: parsing, filtering, dates, safe links, and CSV output.
- `snapshot.html`: the unchanged former `index.html`, retained as both data source and no-JavaScript fallback. Its initial Git blob is `cdb81c402d999b5afc4c0f3ffc73a55a8c8ff71a`.
- `brand/`: existing official marks and PBS Sans font assets, unchanged.

Merge the review branch into `gh-pages`, not `master`, to update the existing Pages publication. No deployment is performed by the test workflow.

To refresh headlines, replace **`snapshot.html`**, not `index.html`. Keep `.meta` (capture date), `.stat b/span` (original collection totals), `ul.stories > li` with its `.is-partner` class, anchor, `.src`, and `.when`, plus the four-column partner table (organization, type, RSS, website).

Snapshot refresh commits include `[skip ci]` so GitHub Actions does not run Playwright for those pushes. Desk, CSS, or test changes still run the checks.

## Data and editorial limits

The browser counts only valid, unique, embedded story links. The source summary includes more headlines than the source page embeds; the desk explains that difference instead of treating unavailable records as search results. Publisher titles and destinations are not rewritten. No topic, location, summary, or editorial importance is inferred from a headline.

Legacy `Fri 10:07 AM` times are resolved against the **snapshot capture date** in `America/New_York`, never the visitor's current date or time zone. Unknown or future times stay unknown and sort last. A fall-back clock hour can be ambiguous because the legacy data has no per-story UTC offset; use full machine-readable publication times in any future data format.

Partner labels follow the supplied invitation list. Directory feed indicators describe the snapshot, not a current health check. No embedded headlines is not a claim that an organization has stopped publishing. The unchanged source remains available for comparison.

## Controls and privacy

Search supports multiple words, quoted phrases, accents, and newsroom names. Combine it with partner/saved scope, newsroom, publication date, and sort order. The list shows 30 rows at a time; CSV exports and printing include **all matching results**. Click a newsroom name to filter its headlines. Press `/` outside a control to focus search.

Bookmarks store article metadata in local storage on this browser, including saved stories from previous snapshots. They do not sync to an account. Shared view links omit the private saved scope. When storage is blocked or full, the current visit still works and the page explains that changes may not persist. Clipboard denial opens a manual-copy dialog.

No analytics, new external runtime dependencies, publisher requests, paywall bypasses, or newsletter sends are added. Snapshot strings are inserted as text; links are restricted to credential-free HTTP(S). CSV fields are quoted and formula-leading cells are neutralized.

## Checks

```sh
node --check assets/desk.mjs
node --check assets/desk-core.mjs
node --test tests/core.test.mjs
python -m pip install playwright==1.55.0
python -m playwright install chromium
python tests/test_browser.py
```

The GitHub workflow runs against the actual committed snapshot on pull requests to `gh-pages`. Browser checks cover filtering, saving/removal, old bookmarks, URL navigation, CSV, printing, clipboard denial, blocked storage, malformed snapshots, unsafe links, JavaScript-disabled fallback, reduced motion, and reflow at 320–1920 pixels. Desktop, dark, and mobile screenshots are uploaded as `news-desk-previews` artifacts.
