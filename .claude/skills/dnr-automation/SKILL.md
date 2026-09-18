---
name: dnr-automation
description: Automate Around New Jersey (NJ PBS) collection and the Daily News Roundup Mailchimp newsletter. Use for the partner-starred snapshot (scripts/build_around_nj_demo.py), RSS/Airtable collection, classification, previews, and Mailchimp drafts. Triggers: Around New Jersey, DNR, News Commons partners, NJ PBS feed.
allowed-tools: Bash, Read, Glob, Grep
---

# Around New Jersey and DNR automation

## When to Activate

Activate this skill when:
- User wants the NJ PBS Around New Jersey snapshot or partner-starred feed
- User wants to run the DNR newsletter pipeline
- User mentions "create newsletter", "run DNR", or "generate preview"
- Troubleshooting pipeline issues
- Testing story collection or classification
- Checking story counts or feed connectivity

## Around New Jersey snapshot

This does **not** create a Mailchimp draft. It writes branded HTML only.

```bash
python scripts/build_around_nj_demo.py --output drafts/around-nj-demo.html
```

Publish by copying that file to `index.html` on the `gh-pages` branch. Live URL: https://centercoopmedia.github.io/around-nj/

## Core Concepts

**The 7-Step Workflow**:
```
1. Fetch → RSS (75+) + Airtable + optional Playwright
2. Enrich → Optional Gemini API summaries
3. Classify → Claude Haiku assigns sections
4. Review → Approve Airtable submissions (triggers email)
5. Preview → Generate HTML, open in browser
6. Refine → Natural language feedback loop
7. Publish → Create Mailchimp draft
```

**Date-Aware Fetching**:
| Day | Lookback | Reason |
|-----|----------|--------|
| Monday | 76 hours | Covers Fri 5am - now (weekend) |
| Tue-Thu | 36 hours | Standard daily coverage |
| Fri-Sun | Warning | Not normal publish days |

**Execution Modes**:
| Flag | Purpose |
|------|---------|
| (none) | Full pipeline with Mailchimp draft |
| --preview | Generate HTML only, no Mailchimp |
| --dry-run | Story counts only, no output |
| --playwright | Include Playwright scraping |
| --enrich | Add Gemini URL enrichment |

## Practical Guidance

### Quick Start Commands

```bash
cd /home/user/dnr

# Standard workflow (recommended)
venv/Scripts/python.exe src/workflow.py

# With Playwright for paywalled sites
venv/Scripts/python.exe src/workflow.py --playwright

# Preview only (testing)
venv/Scripts/python.exe src/main.py --preview

# Quick story count check
venv/Scripts/python.exe src/main.py --dry-run

# Test API connections
venv/Scripts/python.exe src/test_connections.py
```

### Newsletter Sections

| Section | Internal Name | Story Count |
|---------|---------------|-------------|
| Top stories | top_stories | 3-6 max |
| Politics + government | politics | 5-15 |
| Housing + development | housing | 3-10 |
| Work + education | education | 3-10 |
| Health + safety | health | 3-10 |
| Climate + environment | environment | 3-10 |
| Lastly | lastly | 5-20 |

### Troubleshooting

**Pipeline fails with API errors:**
- Run `src/test_connections.py` to verify credentials
- Check `.env` file has all required keys

**Low story count:**
- Try `--hours 48` for broader window
- Check RSS feed health
- Run with `--playwright` for paywalled sites

**Classification issues:**
- Review `src/classifier.py` section descriptions
- Use feedback loop in Step 6 to move stories

## Examples

**Input**: "Refresh the Around New Jersey demo"

**Output**: Snapshot only, no Mailchimp:
```bash
python scripts/build_around_nj_demo.py --output drafts/around-nj-demo.html
```

**Input**: "Run the newsletter"

**Output**: Execute standard workflow:
```bash
cd /home/user/dnr
venv/Scripts/python.exe src/workflow.py
```

**Input**: "Just preview, don't create Mailchimp draft"

**Output**: Run preview mode:
```bash
venv/Scripts/python.exe src/main.py --preview
```

**Input**: "How many stories do we have today?"

**Output**: Run dry-run:
```bash
venv/Scripts/python.exe src/main.py --dry-run
```

## Guidelines

1. Always run from /home/user/dnr directory
2. Use workflow.py for interactive production runs
3. Use main.py with flags for automated/testing runs
4. Check test_connections.py if APIs fail
5. Monday newsletters need full weekend coverage

## Integration

- **dnr-quality-audit**: Audit after preview generation (Step 5)
- **dnr-editorial-feedback**: Process feedback during Step 6
- **dnr-feed-health**: Diagnose if stories are missing
- **dnr-airtable-triage**: Speed up Step 4 review

## File References

- Workflow script: `src/workflow.py`
- Pipeline script: `src/main.py`
- Connection test: `src/test_connections.py`
- Output directory: `drafts/`
- Template: `history/dnr-template.html`

## Environment Requirements

```
ANTHROPIC_API_KEY=     # Claude Haiku classification
AIRTABLE_PAT=          # Airtable submissions
AIRTABLE_BASE_ID=
AIRTABLE_TABLE_ID=
MAILCHIMP_API_KEY=     # Campaign creation
MAILCHIMP_SERVER_PREFIX=
MAILCHIMP_LIST_ID=
GEMINI_API_KEY=        # Optional: URL enrichment
```
