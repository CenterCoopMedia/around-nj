# Around New Jersey

NJ PBS News product for a daily, browsable feed of what New Jersey newsrooms are reporting, with [News Commons](https://njnewscommons.org/) partners marked.

Public snapshot: https://centercoopmedia.github.io/around-nj/

The Center for Cooperative Media at Montclair State University builds and operates the collection pipeline. NJ PBS uses the feed for the Around New Jersey segment. Official NJ PBS marks only: white-and-blue logo on navy. Do not use the retired green NJ logo.

## What it does

- Pulls headlines from 75+ New Jersey sources
- Stars organizations that signed up to work with NJ PBS
- Filters to partners only, or shows the statewide layer
- Keeps the Daily News Roundup Mailchimp newsletter as a second output from the same pipeline

This repository used to be `CenterCoopMedia/dnr`. GitHub redirects the old repo URL. The Pages URL is now `/around-nj/`.

## Live demo

https://centercoopmedia.github.io/around-nj/

- All stories / Partners only
- 72-hour RSS snapshot, not a live all-day product
- TAPinto town feeds currently return HTTP 403
- Several USA Today network RSS URLs in `config/rss_feeds.json` currently return 404

Rebuild:

```bash
python scripts/scrape_partner_homepages.py --output drafts/scraped_headlines.json
python scripts/build_around_nj_demo.py \
  --scraped-json drafts/scraped_headlines.json \
  --output drafts/snapshot.html
```

Officejawn timer `around-nj-refresh.timer` runs that at 6:30am and 2:00pm Eastern. Firecrawl covers invitation-list sites with no usable RSS. Facebook pages and outlets with no homepage are still skipped.

Twice-daily publishes use `[skip ci]` and do not run Playwright. Pre-merge CI on pull requests stays on. The news-desk Playwright workflow is off until NJ PBS owns Actions minutes.

See `docs/around-nj-demo.md`.

## Daily News Roundup newsletter

The same `src/` pipeline still produces the Center for Cooperative Media Mailchimp newsletter (Monday through Thursday). That path is unchanged:

```bash
python src/workflow.py
python src/workflow.py --playwright
python src/main.py --preview
```

Windows launchers: `DNR_Standard.bat`, `DNR_Full.bat`.

## Continuous integration

Pull requests and pushes to `master` run:

- `ruff check` and `ruff format --check`
- `pytest` (offline RSS filters)
- gitleaks
- `CI gate`

`master` requires a pull request, the `CI gate` check, and resolved review threads (including for admins).

```bash
ruff check src tests
ruff format --check src tests
pytest -q
```

## Installation

Python 3.11+. API keys for Anthropic, Mailchimp, and Airtable.

```bash
git clone https://github.com/CenterCoopMedia/around-nj.git
cd around-nj
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium   # optional, paywalled sites
```

Create `.env`:

```env
ANTHROPIC_API_KEY=
AIRTABLE_PAT=
AIRTABLE_BASE_ID=
AIRTABLE_TABLE_ID=
MAILCHIMP_API_KEY=
MAILCHIMP_SERVER_PREFIX=us1
MAILCHIMP_LIST_ID=
GEMINI_API_KEY=   # optional
```

## Newsletter sections

| Section | Content type |
| --- | --- |
| Top stories | Statewide policy news, multi-outlet coverage |
| Politics + government | Legislature, elections, courts, municipal government |
| Housing + development | Affordable housing, zoning, real estate policy |
| Work + education | K-12, higher education, school boards |
| Health + safety | Healthcare, public health, hospitals |
| Climate + environment | Offshore wind, clean energy, PFAS, DEP |
| Lastly | Arts, sports, restaurants, human interest |

See `docs/STYLE_GUIDE.md`.

## Project structure

```
around-nj/
├── src/                     # Collection, classify, Mailchimp
├── scripts/                 # Around New Jersey snapshot builder
├── config/rss_feeds.json    # Statewide feeds
├── config/pbs_partners.json # NJ PBS invitation-list partners
├── docs/
├── .github/workflows/ci.yml
└── README.md
```

## Contributing

Internal tool for NJ PBS and the Center for Cooperative Media.

Joe Amditis  
Associate Director of Operations  
amditisj@montclair.edu

## License

Internal use only. Center for Cooperative Media, Montclair State University. NJ PBS marks remain NJ PBS / PBS property.
