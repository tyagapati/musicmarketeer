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
- **Validation**: Pydantic
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
```

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

## Matching Engine

The matching engine scores marketers across 9 dimensions:

1. **Genre Fit** (20%) - Genre overlap and adjacency
2. **Service Fit** (20%) - Coverage of requested services
3. **Budget Fit** (15%) - Price range compatibility
4. **Goal Fit** (10%) - Alignment with artist goals
5. **Maturity Fit** (10%) - Artist tier compatibility
6. **Proof** (10%) - Admin-assessed proof strength
7. **Timezone** (5%) - Timezone proximity
8. **Language** (5%) - Shared languages
9. **Confidence** (5%) - Platform confidence score

All weights are configurable via environment variables.

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


