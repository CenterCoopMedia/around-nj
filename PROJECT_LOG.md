# Project log: Daily News Roundup (DNR) automation

## Project overview

Automation system for the Daily News Roundup Mailchimp newsletter produced by the Center for Cooperative Media at Montclair State University. The newsletter aggregates and curates local journalism news from across the NJ news ecosystem for distribution to the NJ News Commons network.

**Schedule:** Monday through Thursday mornings
**Distribution:** Mailchimp campaign to NJ News Commons subscribers
**Goal:** Automate story collection, classification, and draft creation so Joe only needs to review and click send.

## Session history

### 2026-09-18 - NJ PBS Around New Jersey demo and CI

- Pulled Stefanie's invitation Airtable and the DNR/NJ News Commons base.
- Published a headlines-only GitHub Pages snapshot at https://centercoopmedia.github.io/dnr/ and branded it with official NJ PBS marks (white-and-blue logo on navy, PBS Sans).
- Added Python CI: ruff check, ruff format, pytest, gitleaks, `CI gate`.
- Protected `master`: require a pull request, conversation resolution (including admins), and the `CI gate` check.
- TAPinto RSS is 403. Several USA Today network feed URLs return 404.

### 2025-12-16 - Project initialization, full pipeline implementation

**Setup completed:**
- Created project directory at `C:\Users\Joe Amditis\Desktop\Crimes\sandbox\dnr`
- Initialized git repository
- Created GitHub repo: https://github.com/CenterCoopMedia/dnr (public, under CenterCoopMedia org)
- Set up project structure (src/, config/, tests/, history/)

**Historical data analyzed:**
- 7 CSV files containing ~33,000 lines of historical newsletter data
- 1 HTML Mailchimp template
- Data spans from March 2022 onward

**API integrations completed:**
- Airtable API: Connected, 486 submissions accessible
- Mailchimp API: Connected, 1,977 subscribers on list "Daily News Digest from NJ News Commons"
- Anthropic API: Connected, using Claude Haiku for cost-efficient classification

**Modules built:**
- `src/rss_fetcher.py` - Fetches from 75+ RSS feeds, 28 confirmed working
- `src/airtable_fetcher.py` - Fetches reader/publisher submissions
- `src/classifier.py` - Claude API batch classification into 7 sections
- `src/html_formatter.py` - Generates Mailchimp-compatible HTML from template
- `src/main.py` - Main pipeline orchestrator with --preview and --dry-run modes
- `src/test_connections.py` - API connection testing utility

**RSS feeds configured:**
- 75+ NJ news outlets across 15 categories
- 28 feeds returning articles successfully
- TAPinto feeds return 0 (may need investigation)
- USA Today network feeds return 0 (may need investigation)

**Pipeline test results:**
- Full preview mode successful
- 253 RSS stories + 44 Airtable submissions = 297 total
- Classification distributed across all 7 sections
- Generated 84,038 characters of HTML
- Preview saved to `drafts/dnr-2025-12-16.html`

**Claude skill created:**
- `.claude/skills/dnr-automation/SKILL.md` - Full documentation and commands

---

## Data analysis findings

### Newsletter structure (from HTML template)

The newsletter has 7 content sections, each color-coded:

| Section | Emoji | CSS Class | Accent Color |
|---------|-------|-----------|--------------|
| Top stories | 📰 | section-top-stories | #4A90E2 (blue) |
| Government + politics | 🏛️ | section-politics | #6a1b9a (purple) |
| Housing + development | 🏘️ | section-housing | #00897b (teal) |
| Work + education | 🏫 | section-education | #3949ab (indigo) |
| Health + safety | 🦠 | section-health | #d32f2f (red) |
| Climate + environment | 🌳 | section-environment | #43a047 (green) |
| Before you go | ☝️ | section-lastly | #fb8c00 (orange) |

**Template features:**
- Two CTA blocks: "Submit story" form and "Subscribe" button
- Mailchimp merge tags for date: `*|DATE:l, F j, Y|*`
- Campaign archive link
- MSU footer with logo
- Responsive design (mobile-friendly)

### Story HTML format

Each story follows this exact format:
```html
<li>Headline text (<a href="URL">Source Name</a>)
```

Stories are wrapped in `<ul>` tags within each section. Link colors inherit from section CSS class.

### CSV data format

| Column | Description |
|--------|-------------|
| Date | Timestamp (mixed formats: DD/MM/YYYY HH:MM:SS or YYYY-MM-DD HH:MM:SS) |
| OUTPUT | Pre-formatted HTML `<li>` element |

**Separator rows:** Lines containing `,-` mark boundaries between different newsletter editions.

---

## Source domains identified

### Primary NJ news sources (high frequency)

| Source Name | Domain | Type |
|-------------|--------|------|
| NJ.com | nj.com | Major metro daily |
| NJ Spotlight News | njspotlightnews.org | Nonprofit news |
| NJ Monitor | newjerseymonitor.com | Nonprofit news |
| NJ Globe | newjerseyglobe.com | Political news |
| NorthJersey.com | northjersey.com | Bergen Record / USA Today |
| Press of Atlantic City | pressofatlanticcity.com | Daily newspaper |
| Asbury Park Press | app.com | Daily newspaper |
| TAPinto | tapinto.net | Hyperlocal network |
| ROI-NJ | roi-nj.com | Business news |
| WHYY | whyy.org | Public media (Philly/NJ) |

### Regional/hyperlocal sources

| Source Name | Domain | Coverage |
|-------------|--------|----------|
| 70and73.com | 70and73.com | South Jersey (Burlington/Camden) |
| Morristown Green | morristowngreen.com | Morris County |
| Princeton Perspectives | princetonperspectives.com | Princeton area |
| NJ Pen | njpen.com | Camden County |
| Jersey Digs | jerseydigs.com | Real estate/development |
| MercerMe | mercerme.com | Mercer County |
| NJ Biz | njbiz.com | Business |
| New Jersey Monthly | njmonthly.com | Statewide magazine |
| Jersey Shore Online | jerseyshoreonline.com | Shore communities |
| MyCentralJersey | mycentraljersey.com | Central Jersey |
| Route 40 | rtforty.com | Atlantic County |
| NJ Arts | njarts.net | Arts/culture |
| NJ Indy | njindy.com | News |
| Patch | patch.com | Hyperlocal network |

### National/regional outlets (occasional)

- The Inquirer (Philadelphia)
- New York Times
- Washington Post
- Wall Street Journal
- NBC New York
- Gothamist
- The Guardian
- Associated Press
- WNYC
- HuffPost
- New York Post
- Fox 5
- News12

---

## Topic/category patterns

### Top stories
- Breaking statewide news
- Major policy announcements
- High-profile investigations
- Cannabis legalization updates
- Public safety incidents

### Government + politics
- State legislature activity
- Elections and campaigns
- Political corruption/ethics
- Municipal government
- Courts and judiciary
- Voter registration
- Budget/spending

### Housing + development
- Affordable housing projects
- Real estate market trends
- Zoning decisions
- Rent control
- Homelessness
- Construction/development
- Utility issues

### Work + education
- K-12 schools
- Higher education
- School board elections
- Curriculum controversies
- Teacher issues
- Workforce development

### Health + safety
- COVID-19 updates (historically)
- Public health policy
- Healthcare access
- Mental health
- Crime/safety
- Veterans issues

### Climate + environment
- Offshore wind energy
- Clean energy policy
- Weather events
- Environmental regulations
- Warehouse development
- Bag ban/plastic reduction
- Pollution/Superfund sites

### Before you go (Lastly)
- Human interest stories
- Arts and culture
- Sports
- Community events
- Lighter news
- Recalls/consumer info
- Local achievements

---

## Editorial rules

### Story limits
- **Top Stories:** 3-6 stories maximum
- **Other sections:** No hard limit, but typically 3-5 stories each

### Story grouping/deduplication
- When multiple outlets cover the same story/event, group them into a single listing
- Multi-outlet coverage usually qualifies a story for Top Stories
- Other sections may have occasional grouping but less common
- Stories featured in Top Stories are **excluded** from topic sections (no duplication)

### Grouped story format
```html
<li>Best headline that captures the story (<a href="URL1">Source 1</a>, <a href="URL2">Source 2</a>, <a href="URL3">Source 3</a>)
```

### Source order in grouped stories
- Order discovered, OR
- Outlet whose headline was selected appears first

### Headline selection criteria
- Choose the headline that best captures the essence of the story
- Avoid hyperbolic or clickbait headlines
- Use sentence case (not title case)
- No quotes around headlines

---

## Airtable integration

**Submission form URL:** Linked in each newsletter CTA
**Base ID:** `appGc7YdwCFVYwTK8`
**Table ID:** `tblXV80z8FCTDewts`
**View ID:** `viwA6Is1wI1VyHRVv`

### Submission fields
| Field | Required | Used in newsletter |
|-------|----------|-------------------|
| Story headline | Yes | Yes |
| Story URL | Yes | Yes |
| Brief story summary | No | For classification |
| Submitter name | Yes | No (internal) |
| Submitter email | Yes | No (internal) |
| Subscribe? | Yes | No (internal) |

---

## Current status

- ✅ Completed: Project setup and GitHub repo
- ✅ Completed: Historical data analysis
- ✅ Completed: Source domain identification
- ✅ Completed: Category/topic pattern analysis
- ✅ Completed: HTML format documentation
- ✅ Completed: Editorial rules documented
- ✅ Completed: Airtable integration (PAT, Base, Table, View IDs)
- ✅ Completed: Mailchimp integration (API key, List ID)
- ✅ Completed: Anthropic API integration (Claude Haiku for classification)
- ✅ Completed: RSS feed URLs compiled (75+ sources)
- ✅ Completed: Airtable fetcher module
- ✅ Completed: RSS fetcher module
- ✅ Completed: Story classifier module
- ✅ Completed: HTML formatter module
- ✅ Completed: Main pipeline script
- ✅ Completed: Claude skill for DNR workflow

**Ready for production use.** Run `python src/main.py` to create a Mailchimp draft.

## Key files

| File | Purpose |
|------|---------|
| `PROJECT_LOG.md` | Development log and documentation |
| `README.md` | Project overview and usage |
| `requirements.txt` | Python dependencies |
| `.env` | Environment variables (API keys - not in git) |
| `.env.example` | Environment variable template |
| `src/main.py` | Main pipeline orchestrator |
| `src/rss_fetcher.py` | RSS feed collection module |
| `src/airtable_fetcher.py` | Airtable submissions module |
| `src/classifier.py` | Claude API story classification |
| `src/html_formatter.py` | HTML newsletter generation |
| `src/test_connections.py` | API connection testing utility |
| `config/rss_feeds.json` | RSS feed configuration (75+ sources) |
| `history/*.csv` | Historical newsletter data (7 category files) |
| `history/dnr-template.html` | Mailchimp HTML template |
| `drafts/` | Generated HTML previews |
| `.claude/skills/dnr-automation/SKILL.md` | Claude Code skill documentation |

## Dependencies

**Python packages (requirements.txt):**
- pyairtable - Airtable API client
- mailchimp-marketing - Mailchimp API client
- anthropic - Claude API client
- feedparser - RSS parsing
- beautifulsoup4 - HTML parsing
- requests - HTTP requests
- python-dotenv - Environment management

**External APIs:**
- Airtable API (reader/publisher submissions)
- Mailchimp Marketing API (campaign creation)
- Anthropic Claude API (story classification)

## Architecture decisions

**Confirmed:**
1. **Story sources:** RSS feeds from major outlets + Airtable submissions from readers/publishers
2. **Classification:** AI-assisted (Claude API) based on headline, URL, and summary
3. **Mailchimp:** Create draft campaign for review before sending
4. **Deduplication:** AI clusters related stories, selects best headline, merges sources

**Pipeline:**
```
RSS Feeds (daily poll) ────┐
                           ├──→ Dedupe/Cluster ──→ AI Classification ──→ HTML Format ──→ Mailchimp Draft
Airtable Submissions ──────┘
```

**Still needed:**
- Mailchimp API key

## Future enhancements

- Automated daily runs via Windows Task Scheduler or cron
- Story deduplication across sources
- Priority scoring for story placement
- Analytics on open rates by category
- Source diversity tracking
- Slack/email notifications when draft is ready
