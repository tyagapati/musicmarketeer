# Marketer catalog onboarding

SoundMatch lists **approved marketers and agencies** in a public catalog. Artists request introductions — there are no platform bookings or payouts.

## Admin workflow

### Path A — Marketer applies

1. Share `{APP_URL}/marketer/apply`
2. Admin → **Applications** → Approve
3. Copy portal link from Applications or Marketers page
4. Marketer updates bio, services, genres, contact email in portal

### Path B — Manual add

1. Admin → **Add marketer** (choose solo or agency)
2. Copy portal link from Marketers page

## Onboarding status (Admin → Marketers)

| Badge | Meaning |
|-------|---------|
| Needs profile | Missing bio or services |
| Needs contact email | Profile OK but no email |
| Live | Approved, bio, services, and contact email set |

## Outreach template

```
Hi [Name] — I'm building SoundMatch, a nonprofit tool that matches indie artists with music marketers based on deep campaign fit. We're growing our catalog of solo marketers and agencies.

Apply here (~3 min): [APP_URL]/marketer/apply
```

## After approve

```
You're listed on SoundMatch. Portal: [APP_URL]/marketer/portal/<token>

Please update your bio, services, genres, and contact email so artists can request introductions.
```

Use **Copy onboarding email** on Admin → Marketers.

## Per-marketer verification

1. Admin badge: **Live**
2. Test artist intake matching their genres
3. They appear in match results
4. Intro request creates row in Admin → Introduction requests

**Beta target:** 10+ live catalog marketers before artist outreach.
