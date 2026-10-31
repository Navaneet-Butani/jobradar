# Job sources

All adapters live in `app/integrations/<name>/` and run through `python -m scripts.run_ingest --sources <name>,...`. None need an API key. Every adapter has a rate limiter, and every raw payload is stored, so a source changing shape can be re-parsed without re-fetching.

Undocumented endpoints break without warning. If a source starts failing, check its endpoint by hand before changing code, and please open an issue.

| `--sources` name | Source | How it's pulled | Caveats |
|---|---|---|---|
| `ats` | Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee | Public board APIs per company (`companies.ats_type/ats_slug`), plus auto-discovery | Highest quality. Coverage = how many companies you know (`data/companies.csv`). SmartRecruiters is filtered to India postings |
| `instahyre` | Instahyre | Public job-search JSON API, full corpus | No descriptions anywhere; scores on title and skills |
| `hirist` | Hirist (tech only) | Search JSON API per search term | Search omits descriptions; `scripts.backfill_descriptions --source hirist` fills them |
| `jobspy` | Indeed India | `python-jobspy`, your cities × target titles + remote sweep | JobSpy's other scrapers are broken or irrelevant for India |
| `linkedin` | LinkedIn guest pages | Guest search, small per-run budget at 1 request / 3 s | Cards only; `backfill_descriptions --source linkedin`. Most likely to rate-limit you; off unless you add it |
| `remotive` | Remotive | Open JSON API | Few India-eligible jobs |
| `himalayas` | Himalayas | Open JSON API | Mostly global; filtered by remote scope at match time |
| `arbeitnow` | Arbeitnow | Open JSON API | EU-heavy |
| `remoteok` | RemoteOK | Open JSON API | Small, US-heavy |

## Recommended combinations

- **India onsite or hybrid:** `ats,instahyre,hirist,jobspy`
- **Remote:** `ats,himalayas,remotive` plus the above
- **First run, no setup:** `ats,hirist,remotive,himalayas`

## Not supported

| Source | Why |
|---|---|
| Naukri | Search API requires a signed per-session token (reCAPTCHA); pages are client-rendered. Only a real browser works |
| HiringCafe | Private API; `robots.txt` disallows the search surface |
| Glassdoor, Google Jobs, ZipRecruiter | Broken for India, or wrong geography |
| Wellfound, Foundit | Need browser automation. Candidates if someone builds a Playwright-based adapter |

Never scrape personal profiles. Job posts only.

## Ideas (contributions welcome)

Indian companies increasingly use **Zoho Recruit, Keka, Darwinbox, Freshteam and Workable**. Each exposes public career pages, and an adapter for any of them, plus discovery like `app/integrations/ats/discovery.py`, would add thousands of jobs. See [adding-a-source.md](adding-a-source.md).
