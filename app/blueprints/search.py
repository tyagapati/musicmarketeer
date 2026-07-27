"""Search, browse, and connect artists with catalog marketers."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app import db
from app.constants.marketer_taxonomy import canonicalize_genre, canonicalize_service
from app.models import CampaignBrief, IntroRequest, CampaignStrategy, MatchFeedback
from app.services.catalog import catalog_marketers_query, format_price_range, get_catalog_marketer
from app.services.matching import rank_marketers
from app.services.notifications import notify_intro_request, notify_match_feedback
search_bp = Blueprint("search", __name__)


def _browse_query():
    genre = canonicalize_genre(request.args.get("genre", "").strip()) or request.args.get("genre", "").strip()
    service = canonicalize_service(request.args.get("service", "").strip()) or request.args.get("service", "").strip()
    min_proof = request.args.get("min_proof", type=int)
    max_budget = request.args.get("max_budget", type=int)

    marketers = catalog_marketers_query().limit(100).all()
    if genre:
        marketers = [m for m in marketers if genre in (m.genres or [])]
    if service:
        marketers = [m for m in marketers if service in (m.services or [])]
    if min_proof:
        marketers = [m for m in marketers if (m.proof_strength or 0) >= min_proof]
    if max_budget:
        marketers = [
            m
            for m in marketers
            if (m.price_min or 0) <= max_budget or (m.price_max or 999999) <= max_budget
        ]
    return marketers


@search_bp.route("/match/<int:brief_id>", methods=["GET", "POST"])
def match(brief_id):
    brief = CampaignBrief.query.get_or_404(brief_id)
    results = rank_marketers(brief, top_n=5)
    strategy = CampaignStrategy.query.filter_by(brief_id=brief.id).first()
    analysis = brief.music_analysis
    existing_feedback = MatchFeedback.query.filter_by(brief_id=brief.id).all()

    if request.method == "POST":
        marketer_id = request.form.get("marketer_id", type=int)
        hired = request.form.get("hired") == "yes"
        rating = request.form.get("rating", type=int)
        notes = request.form.get("notes", "").strip()
        if not marketer_id:
            flash("Select a marketer to leave feedback.", "error")
        else:
            row = MatchFeedback.query.filter_by(brief_id=brief.id, marketer_id=marketer_id).first()
            if not row:
                row = MatchFeedback(brief_id=brief.id, marketer_id=marketer_id)
                db.session.add(row)
            row.hired = hired
            row.rating = rating if rating and 1 <= rating <= 5 else None
            row.notes = notes
            db.session.commit()
            notify_match_feedback(row, brief)
            flash("Thanks — your feedback helps us improve future matches.", "success")
        return redirect(url_for("search.match", brief_id=brief.id))

    return render_template(
        "search_match.html",
        brief=brief,
        results=results,
        strategy=strategy,
        analysis=analysis,
        existing_feedback={f.marketer_id: f for f in existing_feedback},
        catalog_count=catalog_marketers_query().count(),
    )

@search_bp.route("/browse")
def browse():
    view_all = request.args.get("view") == "all"
    marketers = _browse_query() if view_all else catalog_marketers_query().limit(50).all()
    marketer_carousel_pages = [marketers[i : i + 3] for i in range(0, len(marketers), 3)]
    testimonials = _testimonials_from_catalog(marketers)
    return render_template(
        "search_browse.html",
        marketers=marketers,
        marketer_carousel_pages=marketer_carousel_pages,
        view_all=view_all,
        testimonials=testimonials,
        platform_count=len(marketers),
        filters={
            "genre": request.args.get("genre", ""),
            "service": request.args.get("service", ""),
            "min_proof": request.args.get("min_proof", ""),
            "max_budget": request.args.get("max_budget", ""),
        },
    )


@search_bp.route("/marketer/<int:id>", methods=["GET", "POST"])
def marketer_profile(id):
    m = get_catalog_marketer(id)
    if not m:
        abort(404)
    brief_id = request.args.get("brief_id", type=int) or request.form.get("brief_id", type=int)
    brief = CampaignBrief.query.get(brief_id) if brief_id else None

    if request.method == "POST":
        artist_name = request.form.get("artist_name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()
        if not artist_name or not email:
            flash("Name and email are required to request an introduction.", "error")
        else:
            intro = IntroRequest(
                marketer_id=m.id,
                artist_name=artist_name,
                email=email,
                message=message,
                brief_id=brief.id if brief else None,
                intro_type="self_serve",
                status="pending",
            )
            db.session.add(intro)
            db.session.commit()
            notify_intro_request(intro, m)
            flash("Introduction request sent. The marketer will be in touch.", "success")
            if brief:
                return redirect(url_for("search.match", brief_id=brief.id))
            return redirect(url_for("search.marketer_profile", id=m.id))

    return render_template(
        "marketer_profile.html",
        marketer=m,
        brief=brief,
        price_range=format_price_range(m),
    )


def _testimonials_from_catalog(marketers):
    rows = []
    for m in marketers:
        if not m.bio:
            continue
        snippet = (m.bio or "")[:180]
        if len(snippet) < 40:
            continue
        rows.append({"quote": snippet, "brand": m.brand_name or m.name, "proof": m.proof_strength or 0})
        if len(rows) >= 3:
            break
    return rows
