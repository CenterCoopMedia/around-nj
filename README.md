# Daily News Roundup (DNR)

Automated newsletter production for the Daily News Roundup, a Mailchimp newsletter from the [Center for Cooperative Media](https://centerforcooperativemedia.org) at Montclair State University.

The newsletter aggregates New Jersey journalism for the NJ News Commons network. The same feed list now also powers an [Around New Jersey](https://centercoopmedia.github.io/dnr/) demo for NJ PBS: headlines from statewide sources, with News Commons partners marked.

## Features

- **Automated news aggregation** from 75+ NJ news sources via RSS feeds
- **User submissions** via Airtable integration with notification automation
- **AI-powered classification** using Claude Haiku to categorize stories into 7 sections
- **Smart content filtering** to exclude crime, sports scores, lottery results, etc. from top stories
- **Playwright scraping** for paywalled sites (NorthJersey.com, Asbury Park Press, Press of Atlantic City)
- **Interactive workflow** with natural language feedback for refining story selection
- **Mailchimp integration** for draft campaign creation
- **Date-aware fetching** (36 hours for Tue-Thu, weekend coverage for Monday)

## Newsletter sections

| Section | Content type |
|---------|--------------|
| Top stories | Major statewide policy news, stories with multi-outlet coverage |
| Politics + government | Legislature, elections, courts, municipal government |
| Housing + development | Affordable housing, zoning, real estate policy |
| Work + education | K-12, higher education, school boards |
| Health + safety | Healthcare, public health, hospitals |
| Climate + environment | Offshore wind, clean energy, PFAS, DEP actions |
| Lastly | Arts, sports, restaurants, human interest |

## Around New Jersey demo

Live snapshot: https://centercoopmedia.github.io/dnr/

NJ PBS asked for a browsable daily view of what News Commons partners are reporting, for an Around New Jersey segment. The GitHub Pages demo uses official NJ PBS marks (white-and-blue logo on navy, PBS Sans, PBS blue). It is a 72-hour RSS snapshot, not a live product.

- Partners only: filter control on the page
- TAPinto town feeds currently return HTTP 403
- USA Today network RSS URLs in `config/rss_feeds.json` currently return 404

See `docs/around-nj-demo.md`.

## Continuous integration

Pull requests and pushes to `master` run GitHub Actions:

- `ruff check` and `ruff format --check`
- `pytest` (offline RSS filters)
- gitleaks secret scan
- a `CI gate` job that must pass

`master` requires a pull request, the `CI gate` check, and resolved review threads (including for admins).

```bash
ruff check src tests
ruff format --check src tests
pytest -q
```

## Installation

### Prerequisites

- Python 3.11+
- Windows (batch files provided) or Linux/Mac
- API keys for Anthropic, Mailchimp, Airtable

### Setup

```bash
# Clone the repository
git clone https://github.com/CenterCoopMedia/dnr.git
cd dnr

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (for paywalled sites)
playwright install chromium
```

### Configuration

Create a `.env` file with your API credentials:

```env
# Anthropic (required)
ANTHROPIC_API_KEY=your_key_here

# Airtable (required)
AIRTABLE_PAT=your_personal_access_token
AIRTABLE_BASE_ID=your_base_id
AIRTABLE_TABLE_ID=your_table_id

# Mailchimp (required)
MAILCHIMP_API_KEY=your_api_key
MAILCHIMP_SERVER_PREFIX=us1  # or your server prefix
MAILCHIMP_LIST_ID=your_audience_id

# Google Gemini (optional, for URL enrichment)
GEMINI_API_KEY=your_key_here
```

## Usage

### Quick start (Windows)

```bash
# Standard workflow (RSS + Airtable)
DNR_Standard.bat

# Full workflow (includes Playwright for paywalled sites)
DNR_Full.bat
```

### Command line

```bash
# Interactive workflow
python src/workflow.py

# With Playwright sources
python src/workflow.py --playwright

# With URL enrichment
python src/workflow.py --enrich

# Custom time range (hours back)
python src/workflow.py --hours 48

# Direct pipeline (no interactive prompts)
python src/main.py --preview
python src/main.py --dry-run
```

## Workflow

The interactive workflow has 7 steps:

1. **Fetch stories** - Collects from RSS feeds, Airtable, and optionally Playwright
2. **Enrich stories** (optional) - Uses Gemini API to extract context from URLs
3. **Classify stories** - Claude Haiku assigns each story to a section
4. **Review Airtable submissions** - Approve source/section for user submissions
5. **Generate HTML preview** - Creates preview file in `drafts/`
6. **Review and refine** - Natural language feedback loop
7. **Create Mailchimp draft** - Ready for final review and send

### Natural language feedback

During step 6, you can refine the newsletter using plain English:

```
Feedback: Move the NJ Transit story to politics
    ✓ Moved 'nj transit...' from top_stories to politics

Feedback: Remove the carjacking story from top stories
    ✓ Removed 'carjacking...' from top_stories

Feedback: done
```

## Project structure

```
dnr/
├── src/
│   ├── workflow.py          # Interactive 7-step workflow
│   ├── main.py              # Pipeline orchestrator
│   ├── rss_fetcher.py       # RSS feed collection
│   ├── airtable_fetcher.py  # User submission handling
│   ├── classifier.py        # AI classification + filters
│   ├── html_formatter.py    # HTML generation
│   ├── playwright_fetcher.py # Paywalled site scraping
│   └── url_enricher.py      # Gemini URL context
├── config/
│   └── rss_feeds.json       # RSS feed configuration (75+ sources)
├── history/
│   ├── dnr-template.html    # Mailchimp HTML template
│   └── *.csv                # Historical newsletter data
├── .github/workflows/ci.yml # Ruff, pytest, gitleaks, CI gate
├── docs/
│   ├── STYLE_GUIDE.md       # Story selection criteria
│   └── around-nj-demo.md    # NJ PBS Around New Jersey snapshot
├── drafts/                  # Generated HTML previews
├── DNR_Standard.bat         # Quick launch (standard)
├── DNR_Full.bat             # Quick launch (with Playwright)
├── requirements.txt         # Python dependencies
├── CLAUDE.md                # Claude Code instructions
└── README.md                # This file
```

## Content filtering

The system automatically filters inappropriate content from top stories:

**Blocked from top_stories:**
- Crime stories (carjacking, murder, robbery, shooting)
- Car crashes and accidents
- High school sports scores and schedules
- Gift guides and shopping deals
- Lottery and Powerball results
- Restaurant reviews and food rankings
- Expensive house sale stories

**Filtered entirely:**
- Generic broadcast announcements ("WHYY Newscast for Tuesday...")
- Non-NJ content (NYC-only, national news without NJ angle)

See `docs/STYLE_GUIDE.md` for complete story selection criteria.

## API usage

| Service | Purpose | Model |
|---------|---------|-------|
| Anthropic | Story classification | Claude 3 Haiku |
| Anthropic | Feedback processing | Claude 3 Haiku |
| Mailchimp | Campaign creation | Marketing API |
| Airtable | User submissions | REST API |
| Google | URL enrichment | Gemini 2.0 Flash |

## Schedule

The newsletter publishes Monday through Thursday mornings:
- **Monday:** Covers Friday 5am through Monday morning (~76 hours)
- **Tuesday-Thursday:** Covers last 36 hours
- **Friday-Sunday:** Not normal publish days (warning shown)

## Contributing

This is an internal tool for the Center for Cooperative Media. For questions or issues, contact:

**Joe Amditis**
Associate Director of Operations
amditisj@montclair.edu

## License

Internal use only - Center for Cooperative Media, Montclair State University
