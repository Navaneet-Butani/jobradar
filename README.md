<div align="center">

# 📡 JobRadar

### Your personal job radar for Indian software engineers.

**Stop scrolling five job boards every morning.** JobRadar pulls IT jobs from 9+ sources, merges the duplicates, scores every job against *your* profile from 0–100, explains each score, and pings your phone when a strong match lands.

Self-hosted · Open source · Runs on free tiers for **₹0/month**

[![CI](https://github.com/Navaneet-Butani/jobradar/actions/workflows/ci.yml/badge.svg)](https://github.com/Navaneet-Butani/jobradar/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)
![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)
![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)

[Quick start](#-quick-start-5-minutes) · [Features](#-what-you-get) · [Deploy free](#-deploy-for-0month) · [Sources](#-sources) · [Contribute](#-contributing)

</div>

---

> Job boards show you everything. **JobRadar shows you the 20 jobs worth your morning, and why.**

<table>
  <tr>
    <td width="50%"><img src="docs/screenshot-feed.png" alt="Match feed: jobs ranked against your profile"></td>
    <td width="50%"><img src="docs/screenshot-job.png" alt="Job page with the score breakdown"></td>
  </tr>
  <tr>
    <td align="center"><b>Match feed</b>: every job scored against your profile, best first</td>
    <td align="center"><b>Why this score</b>: a transparent breakdown, not a black box</td>
  </tr>
</table>

## 😩 The problem

If you're job hunting in Indian tech, your morning looks like this: Naukri, LinkedIn, Instahyre, Hirist, Indeed, ten company career pages. The same job appears on four sites. Half the "remote" roles are US-only. A third are staffing agencies reposting the same C2H listing. You find the good one three days late.

## ✨ What you get

| | |
|---|---|
| 🇮🇳 **Built for India** | Instahyre, Hirist, Indeed India, LinkedIn, and company career boards. Knows Bengaluru = Bangalore and Gurugram = Gurgaon. Hides US-only "remote" jobs. |
| 🧹 **One job, once** | Cross-posted duplicates are merged. You get the best apply link, and the company's own careers page wins. |
| 🎯 **A score you can read** | 0–100 per job: skills 35 · title 20 · experience 15 · location 10 · freshness 10 · salary 5 · source 5. Click any job to see exactly why it scored that way. |
| 🚫 **Noise filter** | Penalises staffing/C2H listings, "stack spam" descriptions that list 40 technologies, ghost reposts, and mandatory-CS-degree filters. |
| 📄 **Set up from your resume** | Upload your resume and press **Fill from resume**. Skills, target titles, experience and cities are suggested for you to review. |
| 📱 **Alerts on your phone** | New strong matches go to **Telegram, Discord, Slack or ntfy** after every run, each job once. |
| 🏢 **A company list that grows** | When any source mentions a company, JobRadar finds its Greenhouse / Lever / Ashby / SmartRecruiters / Recruitee board and polls it directly from then on. |
| 🗂️ **Application tracker** | Kanban board, follow-up reminders, and an application packet with a tailored summary, pre-filled answers and the recruiter contact. |
| ✉️ **Outreach from your own Gmail** | Paced emails you write and approve, with reply and bounce tracking over IMAP. |
| 🤖 **Any AI, or none** | Gemini free tier, any OpenAI-compatible API (Groq, OpenRouter, OpenAI) or a **fully local model via Ollama** re-ranks top matches with a one-line "why this fits you". Without one, the rule-based scoring still works. |
| 🔒 **Yours, and private** | Self-hosted and invite-only. Your resume and applications stay in your database. **It never auto-applies.** You press send, always. |

## 🆚 Why not just use the job boards?

| | Job boards | JobRadar |
|---|:---:|:---:|
| Jobs from many boards in one feed | ❌ | ✅ |
| Duplicates merged | ❌ | ✅ |
| Ranked against *your* skills and experience | Partly | ✅ |
| Explains each ranking | ❌ | ✅ |
| Filters out staffing spam and US-only "remote" | ❌ | ✅ |
| Polls companies' own career pages directly | ❌ | ✅ |
| Phone alerts for strong matches only | Noisy | ✅ |
| Your data stays with you | ❌ | ✅ |
| Cost | Free or ₹₹₹ for "premium" | **₹0** |

## 🚀 Quick start (5 minutes)

```bash
git clone https://github.com/Navaneet-Butani/jobradar && cd jobradar
cp .env.example .env    # set SECRET_KEY (see the comment in the file)
docker compose up -d --build

# one-time setup
docker compose exec api python -m scripts.create_admin --email you@example.com --name "Your Name"
docker compose exec api python -m scripts.seed_companies

# pull jobs (these sources need no API keys), then open http://localhost:3000
docker compose exec api python -m scripts.run_ingest --sources ats,hirist,remotive,himalayas
```

Then:

1. Log in and open **Profile**.
2. Upload your resume and press **Fill from resume**, or type your skills, titles, experience and cities.
3. Run `python -m scripts.run_matching` to score jobs now. Later ingests score new jobs automatically.

> 👀 **Just want to look around?** `python -m scripts.seed_demo` creates a demo account with two example profiles.

<details>
<summary><b>Without Docker</b> (Python 3.12 + Node 22 + PostgreSQL)</summary>

```bash
python3.12 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # point DATABASE_URL at your Postgres
alembic upgrade head
python -m scripts.create_admin --email you@example.com
uvicorn app.main:app --reload --port 8000             # API docs at /docs

cd web && npm ci && npm run dev                       # http://localhost:3000
```

Use Python 3.12, not 3.13 or newer: pinned `asyncpg`/`pandas` builds have no wheels for newer versions.
</details>

## 💸 Deploy for ₹0/month

| Piece | Free service |
|---|---|
| Database | Supabase (500 MB; retention jobs keep you inside it) |
| Scheduled ingest, matching, alerts | GitHub Actions, 3 runs a day (no always-on server) |
| API | Render free web service (`render.yaml` included) |
| Web | Vercel hobby |
| Email (optional) | Resend free tier, or any SMTP server |
| AI (optional) | Gemini Flash free tier, Groq free tier, or local Ollama |

Step-by-step guide: **[docs/self-hosting.md](docs/self-hosting.md)**.

## 🔌 Sources

| Source | What | Notes |
|---|---|---|
| **Company career boards**: Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee | Straight from the employer | Highest quality, auto-discovered |
| **Instahyre** | Indian tech jobs | No descriptions published; scored on title and skills |
| **Hirist** | Indian tech jobs | Descriptions filled in from the detail API |
| **Indeed India** (via JobSpy) | Broad coverage | Searched by your cities × titles |
| **LinkedIn** (guest pages) | Broad coverage | Opt-in, small rate-limited budget |
| **Remotive, Himalayas, Arbeitnow, RemoteOK** | Remote boards | Filtered to India-eligible remote |

None need an API key. Naukri and HiringCafe are not supported because both require defeating anti-bot protection. Details in [docs/sources.md](docs/sources.md).

## ⚙️ How it works

```
 9+ sources ──▶ normalise (salary · location · skills · experience)
             ──▶ dedupe ──▶ resolve company ──▶ store raw payload ──▶ Postgres
                                                                        │
     matching: hard filters ▶ weighted score ▶ noise rules ▶ optional AI re-rank
                                                                        │
          FastAPI ──▶ Next.js (feed · search · tracker · outreach)    ──▶ 📱 alerts
```

Ingest and serving are separate: the web app only reads the database, so a broken scraper never slows a page. Raw payloads are kept, so a source that changes shape can be re-parsed without fetching it again. More in [docs/architecture.md](docs/architecture.md).

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2 (async) · PostgreSQL full-text search · Next.js · Tailwind · shadcn/ui · GitHub Actions

## ❓ FAQ

<details>
<summary><b>Is this legal? Will I get banned?</b></summary>

JobRadar only reads public job postings, slowly, with a rate limiter on every source. It never scrapes personal profiles and never submits applications. Some sites' terms restrict automated access, so enable only the sources you're comfortable with. LinkedIn is off by default.
</details>

<details>
<summary><b>Do I need an AI API key?</b></summary>

No. Scoring is rule-based and fully explainable. An AI model only adds a one-line "why this fits you" to top matches and sharpens resume autofill. You can use a free Gemini or Groq key, or run a local model with Ollama.
</details>

<details>
<summary><b>I'm not in Bengaluru. Does it work for my city?</b></summary>

Yes. Set any cities on your profile: onsite, hybrid-acceptable, or remote-only. Searches and scoring follow your profile, and common spellings (Baroda/Vadodara, Gurgaon/Gurugram, Bombay/Mumbai) are understood.
</details>

<details>
<summary><b>Can my friends use my instance?</b></summary>

Yes. It's invite-only: an admin sends invites, and each person keeps their own profiles, feed and tracker.
</details>

<details>
<summary><b>Is it only for India?</b></summary>

It's tuned for India (sources, cities, salary in LPA, remote-eligibility rules), but the ATS boards and remote sources are global. Adding a source for another country is mostly a config block.
</details>

## 🤝 Contributing

The most valuable contributions are small:

- 🏢 **Add companies** to [`data/companies.csv`](data/companies.csv), ideally with their career-board slug. Every row improves coverage for everyone.
- 🔌 **Add a source.** Zoho Recruit, Keka, Darwinbox and Workable are wanted. Most sources are a config block, not a parser: see [docs/adding-a-source.md](docs/adding-a-source.md).
- 🎯 **Improve matching rules**, with a test in `tests/`.

See [CONTRIBUTING.md](CONTRIBUTING.md). If JobRadar saved you a morning of scrolling, **a ⭐ helps other job seekers find it.**

## ⚖️ Responsible use

JobRadar collects public job postings for personal job search. It never scrapes personal profiles and never submits applications. Enable only the sources you are comfortable using, keep request rates low (the built-in rate limiters are on by default), and respect each site's terms. You are responsible for how you run it.

## 📄 License

[MIT](LICENSE)
