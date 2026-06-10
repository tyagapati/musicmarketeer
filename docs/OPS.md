# SoundMatch operations

## Weekly discovery (automated)

Set in `.env`:

```env
DISCOVERY_CRON_SECRET=your-long-random-secret
APP_URL=http://127.0.0.1:8000
```

### Windows Task Scheduler

1. Open Task Scheduler → Create Basic Task → Weekly.
2. Action: Start a program → `powershell.exe`
3. Arguments: `-File "d:\ma\musicmarketeer\scripts\run_discovery_cron.ps1"`
4. Set environment variables for the task (or in user env).

### Linux / Render cron

```bash
0 8 * * 1 APP_URL=https://your-app.com DISCOVERY_CRON_SECRET=... /path/to/scripts/run_discovery_cron.sh
```

## Production database

Use PostgreSQL in production (not SQLite):

```env
DATABASE_URL=postgresql://user:pass@host/dbname
```

The app normalizes `postgres://` and uses `postgresql+psycopg://`.

## Production server

```powershell
pip install gunicorn
.\scripts\start_production.ps1
```

Or:

```bash
gunicorn -w 2 -b 0.0.0.0:8000 --timeout 120 "run:app"
```

## Automation toggles (admin dashboard)

**Auto-approve marketers** is **off by default**. When off:

- Discovery stores new marketers as `pending` (manual approve/reject only)
- Batch “Auto-approve high confidence” is disabled

Turn it on from **Admin → Automation** only after verification eval gates pass (see below).

- **Verify top prices:** Admin → Manage marketers → “Verify top 10 prices”
- **Auto-approve high confidence:** Admin → “Auto-approve high confidence”
- Manually reject non-service profiles after discovery runs

## Verification agent

Discovery uses the in-app verification agent (`app/services/verification_agent.py`):

1. Fetch site corpus → classify profile (hard gate)
2. Optional LLM extraction (schema-validated)
3. Deterministic scoring (`proof_strength`, `confidence_score`)
4. Decision tier: `reject`, `pending` (default), or `auto_approve`

Each run logs a `verification_decisions` row with reason codes and risk flags. Admin → Manage marketers shows agent recommendations.

### Rollout gates (required before auto-approve)

```powershell
pip install -r requirements-dev.txt
python scripts/run_verification_eval.py
pytest tests/test_verification_agent.py -q
```

Enable **Auto-approve marketers** only when:

- Classifier false-positive rate &lt; 5% on golden fixtures
- Classifier recall ≥ 90%
- No auto-approve when `llm_invalid_json` risk flag is present

### Verification environment variables

```env
DISCOVERY_MIN_CONFIDENCE=30
AUTO_APPROVE_MIN_CONFIDENCE=75
AUTO_APPROVE_MIN_PROOF=50
VERIFICATION_MIN_CORPUS_CHARS=500
VERIFICATION_BLOCK_AUTO_APPROVE_ON_RISK=true
VERIFICATION_MIN_PROOF_FOR_ESTIMATED_PRICE=60

# Optional LLM extraction (OpenAI-compatible)
DISCOVERY_LLM_API_URL=
DISCOVERY_LLM_API_KEY=
DISCOVERY_LLM_MODEL=gpt-4o-mini
```

### SerpAPI quota protection

Discovery **excludes domains already in your catalog or blacklist** before vetting, and only runs a **small SerpAPI budget per cycle** (default 2 searches). Queries and result pages **rotate each run** so repeat clicks do not re-fetch the same top results.

```env
DISCOVERY_MAX_SERPAPI_QUERIES=2
DISCOVERY_QUERIES_PER_CYCLE=2
DISCOVERY_SERP_MAX_PAGES=5
```

Set `DISCOVERY_MAX_SERPAPI_QUERIES=0` to disable SerpAPI entirely (seeds/Reddit only).

Risk flags block auto-approve but still allow manual admin approval: `thin_corpus`, `llm_unavailable`, `llm_invalid_json`, `no_review_signals`, `inference_only_taxonomy`, `price_estimated_only`.

## Email notifications (intro requests)

Optional SMTP in `.env`:

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_FROM=noreply@soundmatch.example
ADMIN_NOTIFY_EMAIL=you@example.com
```

Without SMTP, intro notifications are logged to the server console.

## Marketplace (Fiverr-style)

Artists book **platform marketers** (enrolled solos with packages). Agencies are admin-only — not shown in browse or match.

Flow: intake → match (top 3 preview) → marketer profile → **Book package** → order page.

Marketers manage packages in `/marketer/portal/<token>`. Admin → **Marketplace orders**.

Bootstrap existing manual marketers as platform supply:

```powershell
py -3 scripts/bootstrap_platform_supply.py
```

Fees (`.env`): `PLATFORM_FEE_PERCENT=20`, `BUYER_SERVICE_FEE_PERCENT=5`, `REQUIRE_STRIPE_CONNECT=1`.

### Stripe Connect (marketer payouts)

1. Marketer opens portal → **Connect payouts**
2. Completes Stripe Express onboarding
3. Webhook `account.updated` sets `payouts_enabled` on the marketer
4. Checkout uses destination charges + `application_fee_amount` when Connect is ready

With `PAYMENTS_DEV_BYPASS=1`, bookings skip Connect (local testing only).

### Order lifecycle

`pending_payment` → `in_progress` (paid) → `delivered` (marketer) → `completed` (artist confirms + optional rating)

Emails fire on paid / delivered / completed when SMTP is configured.

## Legacy Stripe payments (deprecated)

Brief-level premium unlock / concierge intro is replaced by per-order marketplace checkout.

```env
APP_URL=https://your-app.com
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PRICE_ID=price_...
# Or omit STRIPE_PRICE_ID and use inline amount:
STRIPE_AMOUNT_CENTS=4900
STRIPE_CURRENCY=usd
STRIPE_WEBHOOK_SECRET=whsec_...
PAYMENTS_DEV_BYPASS=0
MATCH_ENROLLED_SOLO_BOOST=0.08
```

### Local testing without Stripe

Set `PAYMENTS_DEV_BYPASS=1` in `.env`. The match page shows full results without checkout.

### Stripe webhook (production)

Point Stripe to `POST /search/stripe/webhook`. Use the Stripe CLI locally:

```bash
stripe listen --forward-to localhost:8000/search/stripe/webhook
```

Copy the webhook signing secret into `STRIPE_WEBHOOK_SECRET`.

### Concierge fulfillment

After payment, artists request a concierge intro from the match page. Admin → **Intro requests** shows pending concierge rows. Send the warm email manually, then mark status **Sent**.

Admin dashboard also lists recent paid briefs and pending concierge count.

## Pre-beta checklist

- Set strong `SECRET_KEY` and `ADMIN_PASSWORD`
- Use PostgreSQL (`DATABASE_URL`) in production
- Set `SOUNDMATCH_SKIP_AUTO_SEED=1`
- Configure Stripe test mode first; verify checkout → webhook → paid brief in admin
- Enroll 10–15 solo marketers via `/marketer/apply` and admin approve
- `/health` should return `{"status":"ok"}` for uptime checks

## Marketer profile portal

Approved marketers receive a portal link after admin approval:

`/marketer/portal/<portal_token>`

They can update services, genres, bio, email, and booking URL (Calendly/Stripe).

## Outcome ranking

Admin → **Refresh hire outcomes** boosts `proof_strength` for marketers with confirmed hires.
Run periodically after artists submit match feedback.
