"""Artist campaign builder — 3-step engine wizard."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.constants.marketer_taxonomy import (
    CANONICAL_GENRES,
    CANONICAL_SERVICES,
    normalize_genre_list,
    normalize_service_list,
)
from app.models import CampaignBrief, CampaignStrategy
from app.services.analysis_pipeline import run_analysis
from app.services.dev_sample_data import DEFAULT_PRESET, SAMPLE_PRESETS, dev_tools_enabled
from app.services.spotify_client import resolve_artist_id
from app.services.strategy_engine import build_strategy, run_strategy

artist_bp = Blueprint("artist", __name__)


def _safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _intake_context():
    ctx = {
        "canonical_genres": CANONICAL_GENRES,
        "canonical_services": CANONICAL_SERVICES,
        "dev_sample_enabled": dev_tools_enabled(),
    }
    if ctx["dev_sample_enabled"]:
        ctx["dev_sample_presets"] = SAMPLE_PRESETS
        ctx["dev_sample_default"] = DEFAULT_PRESET
    return ctx


@artist_bp.route("/intake", methods=["GET", "POST"])
def intake():
    if request.method == "POST":
        f = request.form
        spotify_url = f.get("spotify_artist_url", "").strip()
        if not spotify_url:
            flash("Spotify artist URL is required.", "error")
            return render_template("artist_intake.html", **_intake_context())
        if not resolve_artist_id(spotify_url):
            flash("Enter a valid Spotify artist link (open.spotify.com/artist/...).", "error")
            return render_template("artist_intake.html", **_intake_context())

        genres = normalize_genre_list(f.getlist("genres"))
        if not genres:
            genres = normalize_genre_list(f.get("genres", ""))
        services_needed = normalize_service_list(f.getlist("services_needed"))
        if not services_needed:
            services_needed = normalize_service_list(f.get("services_needed", ""))

        budget_max = _safe_int(f.get("budget_max"), default=500)
        if budget_max <= 0:
            budget_max = 500

        preferred = (f.get("preferred_provider_type") or "either").strip().lower()
        if preferred not in ("solo", "agency", "either"):
            preferred = "either"

        brief = CampaignBrief(
            artist_name=f.get("artist_name", "").strip(),
            email=f.get("email", "").strip(),
            spotify_artist_url=spotify_url,
            spotify_artist_id=resolve_artist_id(spotify_url),
            genres=genres,
            goals=[g.strip() for g in f.get("goals", "").split(",") if g.strip()],
            services_needed=services_needed,
            budget_min=_safe_int(f.get("budget_min")),
            budget_max=budget_max,
            preferred_provider_type=preferred,
            spotify_monthly_listeners=_safe_int(f.get("spotify_monthly_listeners")),
            tiktok_followers=_safe_int(f.get("tiktok_followers")),
            ig_followers=_safe_int(f.get("ig_followers")),
            yt_subscribers=_safe_int(f.get("yt_subscribers")),
            timezone=f.get("timezone", ""),
            languages=[lang.strip() for lang in f.get("languages", "en").split(",") if lang.strip()],
            timeline=f.get("timeline", ""),
            past_marketing_exp=f.get("past_marketing_exp", ""),
            engine_stage="analyzing",
            analysis_status="pending",
        )
        brief.compute_maturity()
        db.session.add(brief)
        db.session.commit()

        flash(
            "Great! Here’s your music analysis — then you’ll get ranked marketer matches.",
            "success",
        )

        try:
            run_analysis(brief.id)
        except Exception as exc:
            flash(f"Analysis had issues but you can continue: {exc}", "error")
            return redirect(url_for("artist.campaign_analysis", id=brief.id))

        return redirect(url_for("artist.campaign_analysis", id=brief.id))

    return render_template("artist_intake.html", **_intake_context())


@artist_bp.route("/campaign/<int:id>/analysis")
def campaign_analysis(id):
    brief = CampaignBrief.query.get_or_404(id)
    analysis = brief.music_analysis
    if not analysis:
        try:
            run_analysis(brief.id)
            analysis = brief.music_analysis
        except Exception as exc:
            flash(str(exc), "error")
    averages = (analysis.audio_features or {}).get("averages", {}) if analysis else {}
    return render_template(
        "campaign_analysis.html",
        brief=brief,
        analysis=analysis,
        averages=averages,
    )


@artist_bp.route("/campaign/<int:id>/strategy", methods=["GET", "POST"])
def campaign_strategy(id):
    brief = CampaignBrief.query.get_or_404(id)
    analysis = brief.music_analysis
    if not analysis:
        run_analysis(brief.id)
        analysis = brief.music_analysis

    if request.method == "POST":
        priorities = normalize_service_list(request.form.getlist("priorities"))
        strategy = brief.campaign_strategy or build_strategy(brief, analysis)
        if priorities:
            strategy.artist_priorities = priorities
        db.session.commit()
        brief.engine_stage = "matched"
        db.session.commit()
        from app.services.notifications import notify_match_ready

        notify_match_ready(brief)
        return redirect(url_for("artist.campaign_matches", id=brief.id))

    strategy = brief.campaign_strategy
    if not strategy:
        strategy = run_strategy(brief.id)

    return render_template(
        "campaign_strategy.html",
        brief=brief,
        analysis=analysis,
        strategy=strategy,
        canonical_services=CANONICAL_SERVICES,
    )


@artist_bp.route("/campaign/<int:id>/matches")
def campaign_matches(id):
    brief = CampaignBrief.query.get_or_404(id)
    if brief.engine_stage not in ("matched", "strategy") and not brief.campaign_strategy:
        return redirect(url_for("artist.campaign_strategy", id=brief.id))
    brief.engine_stage = "matched"
    db.session.commit()
    return redirect(url_for("search.match", brief_id=brief.id))


@artist_bp.route("/campaign/<int:id>/report")
def campaign_report(id):
    brief = CampaignBrief.query.get_or_404(id)
    from app.services.matching import rank_marketers

    analysis = brief.music_analysis
    strategy = brief.campaign_strategy
    if not strategy and analysis:
        run_strategy(brief.id)
        strategy = brief.campaign_strategy
    results = rank_marketers(brief, top_n=5)
    return render_template(
        "campaign_report.html",
        brief=brief,
        analysis=analysis,
        strategy=strategy,
        results=results,
    )


@artist_bp.route("/history", methods=["GET", "POST"])
def history():
    """Email lookup for past campaigns — no password for MVP."""
    briefs = []
    email = ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        if not email:
            flash("Enter the email you used on intake.", "error")
        else:
            briefs = (
                CampaignBrief.query.filter(db.func.lower(CampaignBrief.email) == email)
                .order_by(CampaignBrief.id.desc())
                .all()
            )
            if not briefs:
                flash("No campaigns found for that email.", "error")
    elif request.args.get("email"):
        email = request.args.get("email", "").strip().lower()
        if email:
            briefs = (
                CampaignBrief.query.filter(db.func.lower(CampaignBrief.email) == email)
                .order_by(CampaignBrief.id.desc())
                .all()
            )
    return render_template("artist_history.html", briefs=briefs, email=email)


@artist_bp.route("/brief/<int:id>")
def brief_summary(id):
    brief = CampaignBrief.query.get_or_404(id)
    return render_template("brief_summary.html", brief=brief)
