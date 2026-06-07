"""Search and browse marketers blueprint."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app import db
from app.models import CampaignBrief, IntroRequest, Marketer, MatchFeedback
from app.services.matching import rank_marketers

search_bp = Blueprint("search", __name__)


def _browse_query():
    q = Marketer.query.filter_by(status="approved")
    genre = request.args.get("genre", "").strip()
    service = request.args.get("service", "").strip()
    min_proof = request.args.get("min_proof", type=int)
    max_budget = request.args.get("max_budget", type=int)

    marketers = q.limit(100).all()
    if genre:
        marketers = [m for m in marketers if genre in (m.genres or [])]
    if service:
        marketers = [m for m in marketers if service in (m.services or [])]
    if min_proof:
        marketers = [m for m in marketers if (m.proof_strength or 0) >= min_proof]
    if max_budget:
        marketers = [m for m in marketers if (m.price_min or 0) <= max_budget]
    return marketers


@search_bp.route("/match/<int:brief_id>", methods=["GET", "POST"])
def match(brief_id):
    brief = CampaignBrief.query.get_or_404(brief_id)
    if request.method == "POST":
        marketer_id = request.form.get("marketer_id", type=int)
        hired = request.form.get("hired") == "yes"
        rating = request.form.get("rating", type=int)
        notes = request.form.get("notes", "").strip()
        if marketer_id:
            db.session.add(
                MatchFeedback(
                    brief_id=brief.id,
                    marketer_id=marketer_id,
                    hired=hired,
                    rating=rating,
                    notes=notes,
                )
            )
            db.session.commit()
            flash("Thanks for your feedback.", "success")
        return redirect(url_for("search.match", brief_id=brief.id))

    results = rank_marketers(brief, top_n=5)
    return render_template("search_match.html", brief=brief, results=results)


@search_bp.route("/browse")
def browse():
    view_all = request.args.get("view") == "all"
    marketers = _browse_query() if view_all else Marketer.query.filter_by(status="approved").limit(50).all()
    marketer_carousel_pages = [marketers[i : i + 3] for i in range(0, len(marketers), 3)]
    testimonials = _testimonials_from_catalog(marketers)
    return render_template(
        "search_browse.html",
        marketers=marketers,
        marketer_carousel_pages=marketer_carousel_pages,
        view_all=view_all,
        testimonials=testimonials,
        filters={
            "genre": request.args.get("genre", ""),
            "service": request.args.get("service", ""),
            "min_proof": request.args.get("min_proof", ""),
            "max_budget": request.args.get("max_budget", ""),
        },
    )


@search_bp.route("/marketer/<int:id>/go")
def marketer_go(id):
    m = Marketer.query.filter_by(id=id, status="approved").first_or_404()
    target = m.affiliate_url or m.website
    if not target:
        abort(404)
    return redirect(target)


@search_bp.route("/marketer/<int:id>", methods=["GET", "POST"])
def marketer_profile(id):
    m = Marketer.query.filter_by(id=id, status="approved").first_or_404()
    if request.method == "POST":
        intro = IntroRequest(
            marketer_id=m.id,
            artist_name=request.form.get("artist_name", "").strip(),
            email=request.form.get("email", "").strip(),
            message=request.form.get("message", "").strip(),
        )
        if not intro.artist_name or not intro.email:
            flash("Name and email are required.", "error")
        else:
            db.session.add(intro)
            db.session.commit()
            flash("Intro request sent. The marketer will follow up.", "success")
            return redirect(url_for("search.marketer_profile", id=m.id))
    return render_template("marketer_profile.html", marketer=m)


def _testimonials_from_catalog(marketers):
    rows = []
    for m in marketers:
        if not m.evidence_summary:
            continue
        snippet = m.evidence_summary[:180]
        if len(snippet) < 40:
            continue
        rows.append({"quote": snippet, "brand": m.brand_name or m.name, "proof": m.proof_strength or 0})
        if len(rows) >= 3:
            break
    return rows
