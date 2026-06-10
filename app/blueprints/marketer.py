"""Marketer self-serve onboarding, portal, and package management."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.constants.marketer_taxonomy import (
    CANONICAL_GENRES,
    CANONICAL_SERVICES,
    canonicalize_service,
    normalize_genre_list,
    normalize_service_list,
)
from app.models import Marketer, MarketerApplication, MarketerPackage, MarketplaceOrder
from app.services.connect_onboarding import connect_configured, create_account_link, sync_account_from_stripe
from app.services.notifications import notify_order_delivered
from app.services.payments import payments_dev_bypass

marketer_bp = Blueprint("marketer", __name__)


def _safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


@marketer_bp.route("/apply", methods=["GET", "POST"])
def apply():
    if request.method == "POST":
        f = request.form
        services = normalize_service_list(f.getlist("services"))
        if not services:
            services = normalize_service_list(f.get("services", ""))
        genres = normalize_genre_list(f.getlist("genres"))
        if not genres:
            genres = normalize_genre_list(f.get("genres", ""))
        application = MarketerApplication(
            brand_name=f.get("brand_name", "").strip(),
            website=f.get("website", "").strip(),
            email=f.get("email", "").strip(),
            bio=f.get("bio", "").strip(),
            services=services,
            genres=genres,
        )
        if not application.brand_name or not application.website:
            flash("Brand name and website are required.", "error")
            return render_template(
                "marketer_apply.html",
                canonical_genres=CANONICAL_GENRES,
                canonical_services=CANONICAL_SERVICES,
            )
        db.session.add(application)
        db.session.commit()
        return redirect(url_for("marketer.apply_success"))
    return render_template(
        "marketer_apply.html",
        canonical_genres=CANONICAL_GENRES,
        canonical_services=CANONICAL_SERVICES,
    )


@marketer_bp.route("/apply/success")
def apply_success():
    return render_template("marketer_apply_success.html")


@marketer_bp.route("/portal/<token>", methods=["GET", "POST"])
def portal(token):
    marketer = Marketer.query.filter_by(portal_token=token, status="approved", enrolled=True).first_or_404()
    if request.method == "POST":
        action = request.form.get("action", "profile")
        if action == "add_package":
            service = canonicalize_service(request.form.get("service", "").strip()) or request.form.get(
                "service", ""
            ).strip()
            title = request.form.get("title", "").strip()
            price_dollars = _safe_int(request.form.get("price_dollars"))
            if not service or not title or price_dollars <= 0:
                flash("Service, title, and price are required for a package.", "error")
            else:
                db.session.add(
                    MarketerPackage(
                        marketer_id=marketer.id,
                        service=service,
                        title=title,
                        description=request.form.get("description", "").strip(),
                        price_cents=price_dollars * 100,
                        delivery_days=max(1, _safe_int(request.form.get("delivery_days"), 7)),
                        active=True,
                    )
                )
                db.session.commit()
                flash("Package added.", "success")
            return redirect(url_for("marketer.portal", token=token))

        if action == "toggle_package":
            pkg_id = request.form.get("package_id", type=int)
            pkg = MarketerPackage.query.filter_by(id=pkg_id, marketer_id=marketer.id).first()
            if pkg:
                pkg.active = not pkg.active
                db.session.commit()
                flash("Package updated.", "success")
            return redirect(url_for("marketer.portal", token=token))

        if action == "deliver_order":
            order_id = request.form.get("order_id", type=int)
            order = MarketplaceOrder.query.filter_by(id=order_id, marketer_id=marketer.id).first()
            if order and order.status in ("paid", "in_progress"):
                from datetime import datetime

                order.status = "delivered"
                order.delivered_at = datetime.utcnow()
                db.session.commit()
                notify_order_delivered(order)
                flash("Order marked delivered.", "success")
            return redirect(url_for("marketer.portal", token=token))

        marketer.bio = request.form.get("bio", "").strip()
        marketer.email = request.form.get("email", "").strip()
        marketer.services = normalize_service_list(request.form.getlist("services")) or marketer.services
        marketer.genres = normalize_genre_list(request.form.getlist("genres")) or marketer.genres
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("marketer.portal", token=token))

    packages = MarketerPackage.query.filter_by(marketer_id=marketer.id).order_by(MarketerPackage.created_at.desc()).all()
    orders = (
        MarketplaceOrder.query.filter_by(marketer_id=marketer.id)
        .filter(MarketplaceOrder.status.in_(("paid", "in_progress", "delivered", "completed")))
        .order_by(MarketplaceOrder.created_at.desc())
        .limit(20)
        .all()
    )
    return render_template(
        "marketer_portal.html",
        marketer=marketer,
        packages=packages,
        orders=orders,
        canonical_genres=CANONICAL_GENRES,
        canonical_services=CANONICAL_SERVICES,
        connect_configured=connect_configured(),
        payments_dev_bypass=payments_dev_bypass(),
    )


@marketer_bp.route("/portal/<token>/connect")
def portal_connect(token):
    marketer = Marketer.query.filter_by(portal_token=token, status="approved", enrolled=True).first_or_404()
    if not connect_configured():
        flash("Stripe Connect is not configured yet.", "error")
        return redirect(url_for("marketer.portal", token=token))
    return_url = url_for("marketer.portal_connect_return", token=token, _external=True)
    refresh_url = url_for("marketer.portal", token=token, _external=True)
    try:
        onboarding_url = create_account_link(marketer, return_url=return_url, refresh_url=refresh_url)
    except Exception as exc:
        flash(f"Could not start payout setup: {exc}", "error")
        return redirect(url_for("marketer.portal", token=token))
    return redirect(onboarding_url)


@marketer_bp.route("/portal/<token>/connect/return")
def portal_connect_return(token):
    marketer = Marketer.query.filter_by(portal_token=token, status="approved", enrolled=True).first_or_404()
    if marketer.stripe_connect_account_id:
        sync_account_from_stripe(marketer.stripe_connect_account_id)
    if marketer.payouts_enabled:
        flash("Payout setup complete. You can now receive bookings.", "success")
    else:
        flash("Payout setup in progress. Finish any remaining steps in Stripe if prompted.", "success")
    return redirect(url_for("marketer.portal", token=token))
