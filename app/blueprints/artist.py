"""Artist campaign builder blueprint."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import CampaignBrief
from app.services.notifications import notify_match_ready
from app.constants.marketer_taxonomy import (
    CANONICAL_GENRES,
    CANONICAL_SERVICES,
    normalize_genre_list,
    normalize_service_list,
)

artist_bp = Blueprint("artist", __name__)


def _safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


@artist_bp.route("/intake", methods=["GET", "POST"])
def intake():
    if request.method == "POST":
        f = request.form
        genres = normalize_genre_list(f.getlist("genres"))
        if not genres:
            genres = normalize_genre_list(f.get("genres", ""))
        services_needed = normalize_service_list(f.getlist("services_needed"))
        if not services_needed:
            services_needed = normalize_service_list(f.get("services_needed", ""))
        if not genres:
            flash("Select at least one genre.", "error")
            return render_template(
                "artist_intake.html",
                canonical_genres=CANONICAL_GENRES,
                canonical_services=CANONICAL_SERVICES,
            )
        if not services_needed:
            flash("Select at least one service you need.", "error")
            return render_template(
                "artist_intake.html",
                canonical_genres=CANONICAL_GENRES,
                canonical_services=CANONICAL_SERVICES,
            )
        budget_max = _safe_int(f.get("budget_max"))
        if budget_max <= 0:
            flash("Enter a budget range (max budget is required).", "error")
            return render_template(
                "artist_intake.html",
                canonical_genres=CANONICAL_GENRES,
                canonical_services=CANONICAL_SERVICES,
            )
        brief = CampaignBrief(
            artist_name=f.get("artist_name", "").strip(),
            email=f.get("email", "").strip(),
            genres=genres,
            goals=[g.strip() for g in f.get("goals", "").split(",") if g.strip()],
            services_needed=services_needed,
            budget_min=_safe_int(f.get("budget_min")),
            budget_max=_safe_int(f.get("budget_max")),
            spotify_monthly_listeners=_safe_int(f.get("spotify_monthly_listeners")),
            tiktok_followers=_safe_int(f.get("tiktok_followers")),
            ig_followers=_safe_int(f.get("ig_followers")),
            yt_subscribers=_safe_int(f.get("yt_subscribers")),
            timezone=f.get("timezone", ""),
            languages=[l.strip() for l in f.get("languages", "en").split(",") if l.strip()],
            timeline=f.get("timeline", ""),
            past_marketing_exp=f.get("past_marketing_exp", ""),
        )
        brief.compute_maturity()
        db.session.add(brief)
        db.session.commit()
        notify_match_ready(brief)
        return redirect(url_for("search.match", brief_id=brief.id))
    return render_template(
        "artist_intake.html",
        canonical_genres=CANONICAL_GENRES,
        canonical_services=CANONICAL_SERVICES,
    )


@artist_bp.route("/brief/<int:id>")
def brief_summary(id):
    brief = CampaignBrief.query.get_or_404(id)
    return render_template("brief_summary.html", brief=brief)
