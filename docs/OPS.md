# SoundMatch connection engine — operations

## Overview

SoundMatch is a **nonprofit connection engine**. Artists complete campaign intake, receive ranked marketer/agency matches, and request introductions. There is no in-app payment or booking flow.

## Artist flow

1. `/artist/intake` — campaign builder (requires **Spotify artist URL**)
2. `/artist/campaign/<id>/analysis` — Step 1: music analysis report
3. `/artist/campaign/<id>/strategy` — Step 2: marketing channel recommendations
4. `/search/match/<brief_id>` — Step 3: ranked marketers + introduction requests

## Spotify Web API

Set in `.env`:

```env
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_MARKET=US
```

Create credentials at [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) (Web API / Client Credentials). Redirect URI can be `http://127.0.0.1:8000` if the form requires one.

Verify:

```text
GET http://127.0.0.1:8000/health?spotify=1
```

What we use from Spotify:

| Endpoint | Purpose | New apps |
|----------|---------|----------|
| `GET /artists/{id}` | Genres, followers, popularity | Usually works |
| `GET /artists/{id}/top-tracks` | Track titles for lyrical cues | Often **403** |
| `GET /audio-features` | Danceability/energy/etc. | Often **403** |

When restricted endpoints fail, SoundMatch still runs: artist profile from Spotify + genre-estimated sonic averages + brief-based lyrical essence. Optional Last.fm remains a secondary fallback.

Artists paste a **Spotify artist URL** on intake. Analysis → strategy → matching still work without any API keys (brief heuristic).

Admin → **Introduction requests** to track and mark intros sent.

## Marketer supply

- Public catalog: all `status=approved` marketers (agencies and solos)
- Apply: `/marketer/apply` → admin approve
- Manual add: `/admin/marketers/add`
- Profile portal: `/marketer/portal/<token>`

Discovery still ingests new sites; auto-approve is off by default.

## Weekly discovery (automated)

Set in `.env`:

```env
DISCOVERY_CRON_SECRET=your-long-random-secret
APP_URL=http://127.0.0.1:8000
```

See `scripts/run_discovery_cron.ps1` or `scripts/run_discovery_cron.sh`.

## Production database

```env
DATABASE_URL=postgresql://user:pass@host/dbname
SOUNDMATCH_SKIP_AUTO_SEED=1
```

## Production server

```powershell
pip install gunicorn
.\scripts\start_production.ps1
```

## Email (optional)

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@soundmatch.example
ADMIN_NOTIFY_EMAIL=you@example.com
```

Without SMTP, intro notifications log to the server console.

## Pre-beta checklist

- Set strong `SECRET_KEY` and `ADMIN_PASSWORD`
- Use PostgreSQL in production
- Set `SOUNDMATCH_SKIP_AUTO_SEED=1`
- Verify intake → match → intro request → admin intros
- `/health` returns `{"status":"ok"}`

## Roadmap (engine phases)

- **Phase 1:** Marketplace demolition + full approved catalog — done
- **Phase 2–3:** Campaign wizard (analyze → strategy → connect) — done
- **Phase 4:** Lyrical essence from brief + audience/channel-aware matching — done (no external lyrics API required)
- **Phase 5:** Campaign report, homepage repositioning, MatchFeedback UI, intro email polish — done

Optional later: Spotify Web API, Last.fm, Genius (`GENIUS_ACCESS_TOKEN`), `ANALYSIS_LLM_*` for deeper synthesis.
