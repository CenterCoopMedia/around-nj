# Around New Jersey (NJ PBS) agent instructions

## Project overview

NJ PBS product: a daily, browsable feed of New Jersey newsroom headlines with News Commons partners marked. The Center for Cooperative Media collection pipeline also still produces the Daily News Roundup Mailchimp newsletter.

**Repo:** https://github.com/CenterCoopMedia/around-nj
**Public snapshot:** https://centercoopmedia.github.io/around-nj/
**Newsletter schedule:** Monday through Thursday mornings
**Brand:** Official NJ PBS white-and-blue logo on navy. Do not use the retired green NJ logo.

## Quick start

```bash
# Standard workflow (RSS + Airtable)
DNR_Standard.bat

# Full workflow (includes Playwright for paywalled sites)
DNR_Full.bat

# Or run directly
venv\Scripts\python.exe src/workflow.py --playwright
```

## Workflow steps

1. **Fetch stories** - RSS feeds (75+) + Airtable submissions + Playwright scraping
2. **Enrich stories** (optional) - Gemini API for URL context
3. **Classify stories** - Claude Haiku assigns sections
4. **Review Airtable submissions** - Approve source/section for user submissions (triggers notification email)
5. **Generate HTML preview** - Saved to `drafts/dnr-YYYY-MM-DD.html`
6. **Review and refine** - Natural language feedback loop to move/remove stories
7. **Create Mailchimp draft** - Ready for final review and send

## Key modules

| File | Purpose |
|------|---------|
| `src/workflow.py` | Interactive 7-step workflow with feedback loop |
| `src/main.py` | Pipeline orchestrator |
| `src/rss_fetcher.py` | RSS feed collection (75+ NJ sources) |
| `src/airtable_fetcher.py` | User submission handling |
| `src/classifier.py` | Claude Haiku classification + content filters |
| `src/html_formatter.py` | HTML generation from template |
| `src/playwright_fetcher.py` | Scraping paywalled sites (NorthJersey, APP, Press of AC) |
| `src/url_enricher.py` | Gemini API URL context extraction |

## Newsletter sections

| Section | Internal name | Content type |
|---------|---------------|--------------|
| Top stories | `top_stories` | Major statewide policy news, multi-outlet coverage |
| Politics + government | `politics` | Legislature, elections, courts, municipal gov |
| Housing + development | `housing` | Affordable housing, zoning, real estate policy |
| Work + education | `education` | K-12, higher ed, school boards |
| Health + safety | `health` | Healthcare, public health, hospitals |
| Climate + environment | `environment` | Offshore wind, clean energy, PFAS, DEP |
| Lastly | `lastly` | Arts, sports, restaurants, human interest |

## Content filters

Stories are automatically filtered from `top_stories` if they contain:
- Crime/crashes (carjacked, murder, crash, shooting, etc.)
- High school sports (varsity, state championship, player of week)
- Gift guides/shopping (Black Friday, holiday gifts, deals)
- Lottery results (Powerball, Mega Millions, winning numbers)
- Restaurant reviews (best pizza, new restaurant opens)
- Expensive house sales (mansion sold for $X million)

Generic broadcasts are filtered entirely:
- "WHYY Newscast for Tuesday..."
- "NJ Spotlight News: December 15, 2025"
- "This week on..."

## Date-aware fetching

- **Monday:** Fetches from Friday 5am to now (~76 hours for weekend coverage)
- **Tuesday-Thursday:** Last 36 hours
- **Friday-Sunday:** Warning shown (not normal publish days)

## API integrations

| Service | Purpose | Model/Tier |
|---------|---------|------------|
| Anthropic | Story classification | Claude Haiku |
| Anthropic | Feedback processing | Claude Haiku |
| Mailchimp | Draft campaign creation | Marketing API |
| Airtable | User submissions | REST API |
| Google | URL enrichment (optional) | Gemini 2.0 Flash |

## Environment variables

Required in `.env`:
```
ANTHROPIC_API_KEY=
AIRTABLE_PAT=
AIRTABLE_BASE_ID=
AIRTABLE_TABLE_ID=
MAILCHIMP_API_KEY=
MAILCHIMP_SERVER_PREFIX=
MAILCHIMP_LIST_ID=
GEMINI_API_KEY=  # Optional, for URL enrichment
```

## Local checks

```bash
ruff check src tests
ruff format --check src tests
pytest -q
```

GitHub Actions runs the same checks plus gitleaks. `master` requires the `CI gate` check and resolved review threads.

## Important files

- `config/rss_feeds.json` - RSS feed configuration (75+ sources)
- `history/dnr-template.html` - Mailchimp HTML template
- `docs/STYLE_GUIDE.md` - Story selection criteria for each section
- `docs/around-nj-demo.md` - NJ PBS Around New Jersey snapshot (https://centercoopmedia.github.io/around-nj/)
- `drafts/` - Generated HTML previews
- `.github/workflows/ci.yml` - Ruff, pytest, gitleaks, CI gate

## Editorial rules

1. **Top stories** = Policy news only, no crime/crashes/sports/lottery
2. **Multi-outlet coverage** = Strong signal for top_stories placement
3. **Max 20 stories per section**
4. **Source attribution required** - Stories without sources are skipped
5. **NJ focus required** - Non-NJ content filtered to "skip"

## Airtable automation

When both `Source` and `Section` columns are populated for a submission, an automation triggers to notify the submitter their story was approved for the next edition.

## Natural language feedback

During Step 6, you can refine the newsletter with commands like:
- "Move the NJ Transit story to politics"
- "Remove the carjacking story"
- "Remove all crime stories from top stories"

Type `refresh` to reload preview, `done` when satisfied.

## Common tasks

### Add new RSS feed
Edit `config/rss_feeds.json`, add entry with name, domain, rss_url, coverage, priority.

### Add new source domain mapping
Edit `src/html_formatter.py`, add to `domain_map` dict in `extract_source_from_url()`.

### Add new filter keyword
Edit `src/classifier.py`, add to `TOP_STORIES_EXCLUSION_KEYWORDS` list.

### Add new broadcast pattern to skip
Edit `src/rss_fetcher.py`, add to `SKIP_HEADLINE_PATTERNS` list.
