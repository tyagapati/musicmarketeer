---
name: verification-tuning
description: >-
  Safely tune SoundMatch marketer verification: classifier rules, scoring
  thresholds, and auto-approve gates. Use when changing profile_classifier.py,
  verification_decision.py, verification_agent.py, discovery thresholds, or
  before enabling auto_approve_marketers.
---
# Verification Tuning (SoundMatch)

Use this skill when modifying the marketer verification algorithm or deciding whether to enable auto-approve.

## Canonical files

| File | Purpose |
|------|---------|
| `app/services/profile_classifier.py` | Hard gates: reject listicles, social, editorial |
| `app/services/verification_decision.py` | Scoring, risk flags, decision tiers |
| `app/services/verification_agent.py` | Orchestration and LLM extraction |
| `app/services/verification_schema.py` | LLM JSON validation |
| `app/constants/marketer_taxonomy.py` | Canonical service/genre slugs |
| `tests/verification/fixtures.json` | Golden labeled cases |
| `scripts/run_verification_eval.py` | Rollout metrics CLI |

## Required workflow

### 1. Baseline before any change

```bash
cd d:\ma\musicmarketeer
python scripts/run_verification_eval.py
pytest tests/test_verification_agent.py -q
```

Record FPR, recall, and rollout gate status.

### 2. Make one change at a time

Never change classifier rules, scoring weights, and thresholds in the same diff. Tune one variable, re-run eval, compare.

Common env thresholds (see `.env.example`):

- `DISCOVERY_MIN_CONFIDENCE` (default 30) — reject below this
- `AUTO_APPROVE_MIN_CONFIDENCE` (default 75)
- `AUTO_APPROVE_MIN_PROOF` (default 50)
- `VERIFICATION_MIN_CORPUS_CHARS` (default 500)
- `VERIFICATION_BLOCK_AUTO_APPROVE_ON_RISK` (default true)

### 3. Re-run eval after every change

```bash
python scripts/run_verification_eval.py
pytest tests/test_verification_agent.py -q
```

Rollout gates (must pass before enabling auto-approve):

- Classifier FPR &lt; 5% on golden set
- Classifier recall ≥ 90%
- Zero auto-approves when `llm_invalid_json` risk flag is present

### 4. Update fixtures on admin feedback

When admin rejects a false positive or approves a missed agency:

1. Add a case to `tests/verification/fixtures.json` with `expected_classify` and sample `url`/`title`/`snippet`/`text`
2. Re-run eval until gates pass

### 5. Enable auto-approve checklist

Only after eval passes:

- [ ] `python scripts/run_verification_eval.py` exits 0
- [ ] `pytest tests/test_verification_agent.py` passes
- [ ] New risk flags have test coverage in `tests/test_verification_agent.py`
- [ ] Thresholds documented in `docs/OPS.md`
- [ ] Turn on **Admin → Automation → Auto-approve marketers**

Keep auto-approve **off** by default until the checklist is complete.

## Risk flags (block auto-approve, allow manual approve)

- `thin_corpus` — fetched text below `VERIFICATION_MIN_CORPUS_CHARS`
- `llm_unavailable` — LLM not configured
- `llm_invalid_json` — LLM response failed schema validation
- `no_review_signals` — no reviews and rating &lt; 4.0
- `inference_only_taxonomy` — services/genres from regex only
- `price_estimated_only` — no extracted pricing from page
- `weak_proof_with_estimated_price` — estimated price + low proof

## Decision tiers

| Tier | When |
|------|------|
| `reject` | Not a service profile or confidence &lt; min |
| `pending` | Default; borderline cases and any risk flags |
| `auto_approve` | Toggle on + thresholds + no risk flags |

## Interpreting metrics

- **High FPR** → tighten `BLOCKED_*` patterns in `profile_classifier.py`; add false positives to fixtures
- **Low recall** → relax service signal requirements cautiously; verify with fixtures
- **Too many pending** → adjust thresholds only after FPR stays low

## Do not

- Replace `classify_profile` with pure LLM judgment
- Auto-blacklist from LLM output alone
- Enable auto-approve without running `run_verification_eval.py`
- Change multiple threshold env vars in one tuning session
