"""Artist campaign builder blueprint."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import CampaignBrief

artist_bp = Blueprint("artist", __name__)


@artist_bp.route("/intake", methods=["GET", "POST"])
def intake():
    if request.method == "POST":
        f = request.form
        brief = CampaignBrief(
            artist_name=f.get("artist_name", "").strip(),
            email=f.get("email", "").strip(),
            genres=[g.strip() for g in f.get("genres", "").split(",") if g.strip()],
            goals=[g.strip() for g in f.get("goals", "").split(",") if g.strip()],
            services_needed=[s.strip() for s in f.get("services_needed", "").split(",") if s.strip()],
            budget_min=int(f.get("budget_min") or 0),
            budget_max=int(f.get("budget_max") or 0),
            spotify_monthly_listeners=int(f.get("spotify_monthly_listeners") or 0),
            tiktok_followers=int(f.get("tiktok_followers") or 0),
            ig_followers=int(f.get("ig_followers") or 0),
            yt_subscribers=int(f.get("yt_subscribers") or 0),
            timezone=f.get("timezone", ""),
            languages=[l.strip() for l in f.get("languages", "en").split(",") if l.strip()],
            timeline=f.get("timeline", ""),
            past_marketing_exp=f.get("past_marketing_exp", ""),
        )
        brief.compute_maturity()
        db.session.add(brief)
        db.session.commit()
        return redirect(url_for("search.match", brief_id=brief.id))
    return render_template("artist_intake.html")


@artist_bp.route("/brief/<int:id>")
def brief_summary(id):
    brief = CampaignBrief.query.get_or_404(id)
    return render_template("brief_summary.html", brief=brief)
