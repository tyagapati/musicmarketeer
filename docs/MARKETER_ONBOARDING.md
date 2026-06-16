# Marketer onboarding and recruitment

Operational guide for recruiting solo marketers onto SoundMatch before and during private beta.

## Quick links (local)

| Resource | URL |
|----------|-----|
| Apply form | `{APP_URL}/marketer/apply` |
| Admin applications | `{APP_URL}/admin/applications` |
| Add marketer (warm intro) | `{APP_URL}/admin/marketers/add` |
| Admin marketers | `{APP_URL}/admin/marketers` |

Replace `{APP_URL}` with your `APP_URL` from `.env` (default `http://127.0.0.1:8000`).

## Pre-outreach checklist

- [ ] App runs: `py -3 run.py`
- [ ] `ADMIN_PASSWORD` set in `.env`
- [ ] `py -3 -m pytest` passes
- [ ] One admin dry run: apply → approve → portal → packages → test booking
- [ ] Tracking sheet ready (see `docs/marketer_tracking_template.csv`)
- [ ] Outreach messages drafted (below)

### Stripe test mode (recommended before real artists pay)

1. Stripe Dashboard → **Test mode** → copy Secret key → `STRIPE_SECRET_KEY=sk_test_...`
2. Enable **Connect** → Express accounts
3. Second terminal: `stripe listen --forward-to localhost:8000/search/stripe/webhook`
4. Copy `whsec_...` → `STRIPE_WEBHOOK_SECRET` → restart Flask
5. Set `PAYMENTS_DEV_BYPASS=0` and `REQUIRE_STRIPE_CONNECT=1`
6. Complete Connect in a test marketer portal; book with card `4242 4242 4242 4242`

**Remote marketers** cannot complete Connect against `127.0.0.1`. Use a tunnel (ngrok) or staging deploy and set `APP_URL` to the public HTTPS URL before sending portal links.

**Hybrid:** keep `PAYMENTS_DEV_BYPASS=1` while building supply (packages + bios); enable Stripe before artists pay.

## Admin workflow

### Path A — Marketer applies (preferred)

1. Send apply link in outreach
2. Admin → **Applications** → review → **Approve**
3. Copy **portal link** or **onboarding email** from the applications page
4. Marketer completes portal: packages, bio, Connect (when Stripe enforced)
5. Admin → **Marketers** → confirm **Onboarding: Live** and **Connect OK**

### Path B — Warm intro (you already know them)

1. Admin → **Add marketer** → fill form → creates enrolled marketer + starter package
2. Copy portal link from **Marketers** page
3. Same portal steps as Path A

### Onboarding status (Admin → Marketers)

| Badge | Meaning |
|-------|---------|
| Needs packages | Enrolled but no active package |
| Needs Connect | Packages set; Stripe Connect not complete |
| Almost live | Packages OK; Connect pending or dev bypass off |
| Live | Enrolled, packages, bookable in marketplace |

## Outreach templates

### Initial outreach

```
Hi [Name] — I'm building SoundMatch, a marketplace where indie artists book music marketers directly (playlist pitching, PR, TikTok promo, etc.). We're onboarding a small group of solo marketers for a private beta.

Apply here (takes ~3 min): [APP_URL]/marketer/apply

After approval you'll get a private portal to set your packages and pricing.
```

### After approve (Stripe + public URL)

```
Hi [Name],

You're approved on SoundMatch. Your private portal:
[APP_URL]/marketer/portal/<token>

Please:
1. Add 1–3 packages with your real prices and delivery times
2. Update your bio
3. Complete Connect payouts in the portal so you can receive bookings

We're in test mode for now — live payouts before public launch.

Thanks,
[Your name]
```

Use **Copy onboarding email** on Admin → Marketers to generate this automatically.

### After approve (supply only, no Stripe yet)

```
You're approved. Portal: [URL]/marketer/portal/<token>
Please set your packages and bio. Payout setup will follow when we go live.
```

## Per-marketer verification

1. Admin badge: **Connect OK** (if `PAYMENTS_DEV_BYPASS=0`)
2. Test artist intake matching their genres/services
3. They appear in match results
4. End-to-end book → pay (test card) or dev bypass book
5. Mark **live** on tracking sheet

**Beta supply target:** 10 live marketers before inviting beta artists.

## Existing catalog marketers

Enroll discovery/seed marketers with starter packages:

```powershell
py -3 scripts/bootstrap_platform_supply.py
```

Recruited marketers should still use **Apply** or **Add marketer** for clean intake data.

## Production go-live

1. Deploy with Postgres, `SOUNDMATCH_SKIP_AUTO_SEED=1`, HTTPS `APP_URL`
2. Stripe **live** keys + live webhook
3. Marketers re-complete Connect (test accounts don't transfer to live)
4. Configure SMTP for order emails (see `docs/OPS.md`)
5. `PAYMENTS_DEV_BYPASS=0` on production
