"""Search and browse platform marketers (marketplace)."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app import db
from app.constants.marketer_taxonomy import canonicalize_genre, canonicalize_service
from app.models import CampaignBrief, MarketerPackage, MarketplaceOrder
from app.services.marketplace import (
    active_packages_for_marketer,
    format_price_cents,
    get_platform_marketer,
    marketer_can_accept_payments,
    packages_matching_brief,
    platform_marketers_query,
)
from app.services.marketplace_checkout import create_order_for_package, mark_order_paid, start_checkout
from app.services.matching import rank_marketers
from app.services.payments import handle_stripe_webhook, payments_dev_bypass, payments_enabled

search_bp = Blueprint("search", __name__)


def _browse_query():
    genre = canonicalize_genre(request.args.get("genre", "").strip()) or request.args.get("genre", "").strip()
    service = canonicalize_service(request.args.get("service", "").strip()) or request.args.get("service", "").strip()
    min_proof = request.args.get("min_proof", type=int)
    max_budget = request.args.get("max_budget", type=int)

    marketers = platform_marketers_query().limit(100).all()
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
            if any(p.price_cents <= max_budget * 100 for p in active_packages_for_marketer(m.id))
            or (m.price_min or 0) <= max_budget
        ]
    return marketers


@search_bp.route("/match/<int:brief_id>", methods=["GET", "POST"])
def match(brief_id):
    brief = CampaignBrief.query.get_or_404(brief_id)
    results = rank_marketers(brief, top_n=5)
    preview_limit = 3
    return render_template(
        "search_match.html",
        brief=brief,
        results=results,
        preview_limit=preview_limit,
        format_price_cents=format_price_cents,
        platform_count=platform_marketers_query().count(),
    )


@search_bp.route("/match/<int:brief_id>/book/<int:package_id>", methods=["POST"])
def book_package(brief_id, package_id):
    brief = CampaignBrief.query.get_or_404(brief_id)
    package = MarketerPackage.query.get_or_404(package_id)
    marketer = get_platform_marketer(package.marketer_id)
    if not marketer or not package.active:
        flash("This package is not available.", "error")
        return redirect(url_for("search.match", brief_id=brief.id))
    if not brief.email:
        flash("Your brief needs an email to book a marketer.", "error")
        return redirect(url_for("search.match", brief_id=brief.id))
    if not marketer_can_accept_payments(marketer):
        flash(
            "This marketer is still setting up payouts. Try another match or check back soon.",
            "error",
        )
        return redirect(url_for("search.marketer_profile", id=marketer.id, brief_id=brief.id))

    try:
        order = create_order_for_package(brief=brief, package=package)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("search.marketer_profile", id=package.marketer_id, brief_id=brief.id))

    success_url = (
        url_for("search.order_success", order_id=order.id, _external=True)
        + "?session_id={CHECKOUT_SESSION_ID}"
    )
    cancel_url = url_for("search.marketer_profile", id=marketer.id, brief_id=brief.id, _external=True)

    try:
        checkout_url = start_checkout(order, success_url=success_url, cancel_url=cancel_url)
    except RuntimeError as exc:
        flash(str(exc), "error")
        return redirect(url_for("search.marketer_profile", id=marketer.id, brief_id=brief.id))

    if payments_dev_bypass() or checkout_url.endswith("dev_bypass"):
        flash("Booking confirmed (dev mode). Your marketer will be notified.", "success")
        return redirect(url_for("search.order_detail", order_id=order.id))

    return redirect(checkout_url, code=303)


@search_bp.route("/orders/<int:order_id>")
def order_detail(order_id):
    order = MarketplaceOrder.query.get_or_404(order_id)
    marketer = get_platform_marketer(order.marketer_id)
    package = MarketerPackage.query.get(order.package_id)
    if not marketer:
        abort(404)
    return render_template(
        "order_detail.html",
        order=order,
        marketer=marketer,
        package=package,
        format_price_cents=format_price_cents,
    )


@search_bp.route("/orders/<int:order_id>/success")
def order_success(order_id):
    order = MarketplaceOrder.query.get_or_404(order_id)
    session_id = request.args.get("session_id")
    if mark_order_paid(order, session_id=session_id if session_id != "dev_bypass" else None):
        flash("Payment received. Your booking is confirmed.", "success")
    return redirect(url_for("search.order_detail", order_id=order.id))


@search_bp.route("/orders/<int:order_id>/complete", methods=["POST"])
def order_complete(order_id):
    order = MarketplaceOrder.query.get_or_404(order_id)
    if order.status != "delivered":
        flash("You can confirm completion after the marketer marks the order delivered.", "error")
        return redirect(url_for("search.order_detail", order_id=order.id))

    from datetime import datetime

    from app.services.notifications import notify_order_completed

    rating = request.form.get("rating", type=int)
    notes = request.form.get("review_notes", "").strip()
    if rating is not None and (rating < 1 or rating > 5):
        flash("Rating must be between 1 and 5.", "error")
        return redirect(url_for("search.order_detail", order_id=order.id))

    order.status = "completed"
    order.completed_at = datetime.utcnow()
    if rating:
        order.rating = rating
    if notes:
        order.review_notes = notes
    db.session.commit()
    notify_order_completed(order)
    flash("Thanks — order marked complete.", "success")
    return redirect(url_for("search.order_detail", order_id=order.id))


@search_bp.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        from app.services.payments import _stripe_client

        client = _stripe_client()
        secret = __import__("os").environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
        if secret:
            event = client.Webhook.construct_event(payload, sig_header, secret)
            from app.services.connect_onboarding import handle_account_updated_event
            from app.services.marketplace_checkout import handle_marketplace_webhook_event

            if event.get("type") == "account.updated":
                result = handle_account_updated_event(event)
                if result.get("handled"):
                    return {"ok": True, **result}
            result = handle_marketplace_webhook_event(event)
            if result.get("handled"):
                return {"ok": True, **result}
        handle_stripe_webhook(payload, sig_header)
    except Exception as exc:
        return {"error": str(exc)}, 400
    return {"ok": True}


@search_bp.route("/browse")
def browse():
    view_all = request.args.get("view") == "all"
    marketers = _browse_query() if view_all else platform_marketers_query().limit(50).all()
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


@search_bp.route("/marketer/<int:id>", methods=["GET"])
def marketer_profile(id):
    m = get_platform_marketer(id)
    if not m:
        abort(404)
    brief_id = request.args.get("brief_id", type=int)
    brief = CampaignBrief.query.get(brief_id) if brief_id else None
    packages = packages_matching_brief(m.id, brief.services_needed if brief else [])
    if not packages:
        packages = active_packages_for_marketer(m.id)
    return render_template(
        "marketer_profile.html",
        marketer=m,
        brief=brief,
        packages=packages,
        format_price_cents=format_price_cents,
        payments_enabled=payments_enabled(),
        payments_dev_bypass=payments_dev_bypass(),
        can_book=marketer_can_accept_payments(m),
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
