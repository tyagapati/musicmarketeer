## SoundMatch MVP

A full-stack web application that helps upcoming music artists find the best matching music marketers based on genre, goals, and budget.

## Features

- **Campaign Builder**: Artists fill out a comprehensive form with their music style, goals, budget, and stats
- **Matching Engine**: Rule-based scoring system that ranks marketers against artist briefs with detailed explanations
- **Marketer Directory**: Curated directory of marketers (approved via admin review)
- **Admin Console**: Review, approve, and manage discovered marketers
- **Data Ingestion**: Connectors for discovering marketers from Reddit and web directories

## Tech Stack

- **Backend**: Flask + Flask-SQLAlchemy + Flask-Migrate
- **Database**: SQLite (dev), PostgreSQL-ready
- **Background Jobs**: RQ + Redis (with sync fallback)
- **Optional extras**: RQ + Redis + Praw (`requirements-extra.txt`) for background jobs / Reddit ingestion
- **Templates**: Jinja2 with dark-themed UI

## Setup Instructions

### 1. Clone and Navigate

```bash
cd soundmatch-mvp
```

### 2. Create Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux
python -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
# Optional: worker / Reddit ingestion
pip install -r requirements-extra.txt
```

The main `requirements.txt` is intentionally small so production installs (e.g. Render) stay fast. **`.python-version`** pins **3.12.x** so wheels (especially `psycopg`) install quickly—avoid **3.14** on PaaS unless you know wheels exist.

### 4. Configure Environment

Create a `.env` file in the project root (copy from `.env.example` if available):

```env
FLASK_APP=run.py
FLASK_ENV=development
SECRET_KEY=your-secret-key-here

DATABASE_URL=sqlite:///soundmatch.db

# Optional: Redis for background jobs
REDIS_URL=redis://localhost:6379/0

# Optional: Reddit API credentials
REDDIT_CLIENT_ID=your-reddit-client-id
REDDIT_CLIENT_SECRET=your-reddit-client-secret
REDDIT_USER_AGENT=soundmatch-mvp/1.0
```

### 5. Initialize Database

```bash
flask db init
flask db migrate -m "initial"
flask db upgrade
```

### 6. Seed Sample Data

```bash
python seed.py
```

This will create:
- 10 sample marketers (all approved)
- 2 sample campaign briefs
- Print matching results for both briefs

### 7. Run the Application

```bash
flask run
# or
python run.py
```

Visit `http://localhost:5000`

### 8. (Optional) Run RQ Worker

If you have Redis running and want to process background ingestion jobs:

```bash
rq worker soundmatch
```

## Project Structure

```
soundmatch-mvp/
├── run.py                          # Entry point
├── requirements.txt
├── seed.py                         # Seed script
├── app/
│   ├── __init__.py                 # App factory
│   ├── config.py                   # Configuration
│   ├── models.py                   # SQLAlchemy models
│   ├── blueprints/
│   │   ├── main.py                 # Home page
│   │   ├── artist.py               # Campaign builder
│   │   ├── search.py               # Matching & browsing
│   │   └── admin.py                # Admin dashboard
│   ├── services/
│   │   ├── matching.py             # Matching engine
│   │   └── worker.py               # Background jobs
│   ├── connectors/
│   │   └── base.py                 # Reddit & WebDirectory connectors
│   └── templates/                  # Jinja2 templates
```

## Key Endpoints

### Artist
- `GET /artist/intake` - Campaign builder form
- `POST /artist/intake` - Submit brief
- `GET /artist/brief/<id>` - Brief summary

### Search
- `GET /search/match/<brief_id>` - Get ranked matches
- `GET /search/browse` - Browse approved marketers
- `GET /search/marketer/<id>` - Marketer profile

### Admin
- `GET /admin/` - Dashboard
- `GET /admin/marketers` - List marketers
- `POST /admin/marketers/<id>/approve` - Approve marketer
- `POST /admin/marketers/<id>/reject` - Reject marketer
- `POST /admin/ingest` - Trigger ingestion

## Discovery Agent (new)

The ingestion endpoint now runs a reliability-first pipeline:

1. Discover candidate marketer URLs from connector seeds
2. Vet quality signals (ratings/review counts/evidence)
3. Categorize into matching fields (`services`, `genres`)
4. Save as `pending` marketers for admin approval

### Discovery environment variables

- `DISCOVERY_SEED_URLS`: comma-separated candidate websites to evaluate
- `REDDIT_DISCOVERY_URLS`: optional comma-separated Reddit-found candidate URLs
- `SERPAPI_API_KEY`: optional SerpAPI key for search-based discovery
- `DISCOVERY_SEARCH_RESULTS_PER_QUERY`: search results per query (default `5`)
- `DISCOVERY_MAX_CANDIDATES`: max candidates per cycle (default `25`)
- `DISCOVERY_MIN_CONFIDENCE`: minimum confidence to persist (default `30`)
- `DISCOVERY_LLM_API_URL`: optional OpenAI-compatible chat completions URL
- `DISCOVERY_LLM_API_KEY`: optional API key for LLM extraction
- `DISCOVERY_LLM_MODEL`: optional model name (default `gpt-4o-mini`)
- `REDDIT_DISCOVERY_SUBREDDITS`: optional subreddit list for Reddit API search

### Discovery scheduling

Use any scheduler to call `POST /admin/ingest` at your desired cadence:

- Local/VM cron example:
  - `0 8 * * 1 curl -X POST -H "X-Cron-Secret: YOUR_SECRET" http://localhost:8000/admin/ingest`
- Render example:
  - Add a weekly cron job hitting `/admin/ingest` with header `X-Cron-Secret`.

Set `DISCOVERY_CRON_SECRET` in `.env` for unattended runs. Set `ADMIN_PASSWORD` to protect admin routes.

The discovery cycle automatically biases search queries toward underrepresented
service/genre combinations so your marketer pool keeps expanding coverage.

See `/admin/discovery-report` for coverage and gap analysis.

## Matching Engine

The matching engine scores marketers across 9 weighted dimensions (normalized to 100%):

1. **Genre Fit** (`MATCH_WEIGHT_GENRE`, default 20%)
2. **Service Fit** (`MATCH_WEIGHT_SERVICE`, default 20%)
3. **Budget Fit** (`MATCH_WEIGHT_BUDGET`, default 15%)
4. **Goal Fit** (`MATCH_WEIGHT_GOAL`, default 10%)
5. **Maturity Fit** (`MATCH_WEIGHT_MATURITY`, default 10%)
6. **Proof** (`MATCH_WEIGHT_PROOF`, default 10%) — uses `proof_strength`
7. **Timezone** (`MATCH_WEIGHT_TIMEZONE`, default 5%)
8. **Language** (`MATCH_WEIGHT_LANGUAGE`, default 5%)
9. **Confidence** (`MATCH_WEIGHT_CONFIDENCE`, default 5%) — uses `confidence_score`

Hire feedback and artist ratings provide additional ranking boosts over time. Strategy-aware signals (`audience_fit`, `channel_fit`, `lyrical_themes`) also influence ranking when a campaign analysis exists.

## Artist actions

- **Campaign builder**: `/artist/intake` → music analysis → marketing strategy → ranked matches.
- **Intro requests**: artists submit from marketer profile pages (`IntroRequest` stored for admin review; marketer + admin notified when SMTP is configured).
- **Campaign report**: printable summary at `/artist/campaign/<id>/report`.
- **Match feedback**: artists can report hire outcomes on match results pages.

## Marketer onboarding

Marketers can apply at `/marketer/apply`. Applications appear in `/admin/applications` for review.

### Render build stuck on “Installing dependencies”?

- Much of a long wait is often the **queue** or network, not pip—open the build log and see whether it’s still downloading wheels or waiting.
- Set **Environment → `PYTHON_VERSION`** to **`3.12.8`** (or rely on repo **`.python-version`**) so Render doesn’t default to a very new Python with fewer prebuilt wheels.
- **Clear build cache & deploy** if a previous build left a bad partial install.
- This repo’s slim **`requirements.txt`** avoids optional packages (`praw`, `redis`, `rq`) that aren’t needed for the web UI + Postgres.

## Deploying to Render (PostgreSQL)

1. Create a **PostgreSQL** instance and set **`DATABASE_URL`** on your web service (Render injects this automatically when you link the DB).
2. The app normalizes `postgres://` → `postgresql://` and uses **`postgresql+psycopg://`** so SQLAlchemy talks to **psycopg v3** (what `requirements.txt` installs).
3. On startup, **`db.create_all()`** creates tables if they are missing (there are no committed Alembic revisions yet). If the **`marketers`** table is empty, the app **auto-seeds the same demo catalogue** as `seed.py` (no shell step). Set **`SOUNDMATCH_SKIP_AUTO_SEED=1`** to turn that off. For a full wipe + reseed including sample briefs, run **`python seed.py`** locally or in a one-off job (that script still drops and recreates tables).

## Notes

- Only "approved" marketers appear in public search/matching
- All discovered marketers start as "pending" and require admin review
- Reddit connector uses official OAuth API (no scraping)
- Connectors respect platform ToS and never bypass authentication

## License

MIT


