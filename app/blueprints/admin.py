"""Admin dashboard blueprint."""
import secrets

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app import db
from app.models import (
    CampaignBrief,
    IntroRequest,
    Marketer,
    MarketerApplication,
    MarketerPackage,
    MarketplaceOrder,
    VerificationDecision,
)
from app.constants.marketer_taxonomy import (
    CANONICAL_GENRES,
    CANONICAL_SERVICES,
    normalize_genre_list,
    normalize_service_list,
)
from app.services.connect_onboarding import connect_configured
from app.services.marketplace import marketplace_gmv_stats, platform_marketers_query
from app.services.onboarding import (
    active_package_counts,
    marketer_onboarding_status,
    marketer_portal_url,
    onboarding_email_body,
    provision_from_application,
    provision_platform_marketer,
)
from app.services.payments import payments_dev_bypass
from app.services.verification_decision import would_auto_approve_if_enabled
from app.services.admin_auth import is_admin_authenticated, require_admin, verify_admin_password
from app.services.automation_settings import (
    automation_toggle_states,
    is_automation_enabled,
    set_automation_enabled,
)
from app.services.catalog_qa import auto_approve_high_confidence_pending, verify_top_approved_prices
from app.services.discovery_pipeline import get_discovery_report, run_discovery_cycle
from app.services.outcome_ranking import refresh_outcome_scores
from app.services.site_blacklist import reject_and_remove_marketer
from app.services.site_urls import sync_marketer_domain_fields
from app.services.worker import enqueue

admin_bp = Blueprint("admin", __name__)


def _safe_next_path(path):
    if path and path.startswith("/") and not path.startswith("//"):
        return path
    return None


@admin_bp.before_request
def protect_admin_routes():
    if request.endpoint in ("admin.login", "admin.logout"):
        return None
    if request.endpoint == "admin.ingest" and request.headers.get("X-Cron-Secret"):
        return None
    if not is_admin_authenticated():
        return redirect(url_for("admin.login", next=request.path))


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if verify_admin_password(request.form.get("password", "")):
            session["admin_authenticated"] = True
            return redirect(_safe_next_path(request.args.get("next")) or url_for("admin.index"))
        flash("Invalid admin password.", "error")
    return render_template("admin_login.html")


@admin_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("admin_authenticated", None)
    return redirect(url_for("main.index"))


@admin_bp.route("/")
@require_admin
def index():
    pending = Marketer.query.filter_by(status="pending").count()
    approved = Marketer.query.filter_by(status="approved").count()
    apps_pending = MarketerApplication.query.filter_by(status="pending").count()
    enrolled_platform = platform_marketers_query().count()
    active_packages = MarketerPackage.query.filter_by(active=True).count()
    recent_orders = MarketplaceOrder.query.order_by(MarketplaceOrder.created_at.desc()).limit(5).all()
    pending_orders = MarketplaceOrder.query.filter(
        MarketplaceOrder.status.in_(("paid", "in_progress"))
    ).count()
    gmv = marketplace_gmv_stats()
    return render_template(
        "admin_index.html",
        pending=pending,
        approved=approved,
        apps_pending=apps_pending,
        automation_toggles=automation_toggle_states(),
        enrolled_platform=enrolled_platform,
        active_packages=active_packages,
        recent_orders=recent_orders,
        pending_orders=pending_orders,
        gmv=gmv,
    )


@admin_bp.route("/automation", methods=["POST"])
@require_admin
def update_automation():
    for toggle in automation_toggle_states():
        key = toggle["key"]
        enabled = request.form.get(key) == "on"
        set_automation_enabled(key, enabled)
    flash("Automation settings saved.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/marketers")
@require_admin
def marketers():
    result = {
        "created": request.args.get("created", type=int),
        "skipped_existing": request.args.get("skipped_existing", type=int),
        "skipped_low_confidence": request.args.get("skipped_low_confidence", type=int),
        "skipped_not_profile": request.args.get("skipped_not_profile", type=int),
        "skipped_blacklisted": request.args.get("skipped_blacklisted", type=int),
        "considered": request.args.get("considered", type=int),
        "queued": request.args.get("queued", type=int),
    }
    all_marketers = Marketer.query.order_by(Marketer.status).all()
    latest_decisions = _latest_verification_decisions(all_marketers)
    pkg_counts = active_package_counts([m.id for m in all_marketers])
    onboarding = {
        m.id: marketer_onboarding_status(m, active_packages=pkg_counts.get(m.id, 0))
        for m in all_marketers
    }
    return render_template(
        "admin_marketers.html",
        marketers=all_marketers,
        latest_decisions=latest_decisions,
        onboarding=onboarding,
        result=result,
        auto_approve_enabled=is_automation_enabled("auto_approve_marketers"),
        stripe_configured=connect_configured(),
        payments_dev_bypass=payments_dev_bypass(),
    )


def _latest_verification_decisions(marketers):
    """Map marketer id -> latest VerificationDecision summary."""
    by_id = {m.id: m for m in marketers}
    ids = list(by_id.keys())
    if not ids:
        return {}
    rows = (
        VerificationDecision.query.filter(VerificationDecision.marketer_id.in_(ids))
        .order_by(VerificationDecision.created_at.desc())
        .all()
    )
    latest = {}
    for row in rows:
        if row.marketer_id not in latest:
            marketer = by_id.get(row.marketer_id)
            risk_flags = (row.scores or {}).get("risk_flags", [])
            latest[row.marketer_id] = {
                "decision": row.decision,
                "reason_codes": row.reason_codes or [],
                "risk_flags": risk_flags,
                "would_auto_approve": would_auto_approve_if_enabled(
                    {
                        "is_service_profile": True,
                        "confidence_score": marketer.confidence_score or 0 if marketer else 0,
                        "proof_strength": marketer.proof_strength or 0 if marketer else 0,
                        "services": marketer.services if marketer else [],
                        "genres": marketer.genres if marketer else [],
                        "risk_flags": risk_flags,
                    }
                ),
            }
    return latest


@admin_bp.route("/marketers/<int:id>/enroll", methods=["POST"])
@require_admin
def toggle_enrolled(id):
    m = Marketer.query.get_or_404(id)
    m.provider_type = "solo"
    m.enrolled = not bool(m.enrolled)
    if m.enrolled and not m.portal_token:
        m.portal_token = secrets.token_urlsafe(24)
    if m.enrolled and not MarketerPackage.query.filter_by(marketer_id=m.id, active=True).first():
        service = (m.services or ["playlist_pitching"])[0]
        price = max(49, m.price_min or 149)
        db.session.add(
            MarketerPackage(
                marketer_id=m.id,
                service=service,
                title=f"{m.brand_name or m.name} — starter package",
                description=m.bio or "Bookable package on SoundMatch.",
                price_cents=price * 100,
                delivery_days=14,
                active=True,
            )
        )
    db.session.commit()
    flash(
        f"{'Enrolled' if m.enrolled else 'Unenrolled'} {m.brand_name or m.name} as platform marketer.",
        "success",
    )
    return redirect(url_for("admin.marketers"))


@admin_bp.route("/marketers/<int:id>/approve", methods=["POST"])
@require_admin
def approve(id):
    m = Marketer.query.get_or_404(id)
    m.status = "approved"
    if not m.portal_token:
        m.portal_token = secrets.token_urlsafe(24)
    sync_marketer_domain_fields(m)
    db.session.commit()
    return redirect(url_for("admin.marketers"))


@admin_bp.route("/marketers/<int:id>/reject", methods=["POST"])
@require_admin
def reject(id):
    m = Marketer.query.get_or_404(id)
    brand = m.brand_name or m.name or "site"
    reject_and_remove_marketer(m)
    flash(f"Removed {brand} from the catalog and added its domain to the blacklist.", "success")
    return redirect(url_for("admin.marketers"))


@admin_bp.route("/marketers/<int:id>/verify-price", methods=["POST"])
@require_admin
def verify_price(id):
    m = Marketer.query.get_or_404(id)
    m.price_verified = True
    m.price_source = "verified"
    db.session.commit()
    return redirect(url_for("admin.marketers"))


@admin_bp.route("/catalog/verify-top-prices", methods=["POST"])
@require_admin
def catalog_verify_top_prices():
    result = verify_top_approved_prices(limit=10)
    flash(f"Verified prices for {result['verified']} of top {result['considered']} marketers.", "success")
    return redirect(url_for("admin.marketers"))


@admin_bp.route("/catalog/auto-approve", methods=["POST"])
@require_admin
def catalog_auto_approve():
    result = auto_approve_high_confidence_pending()
    if result.get("disabled"):
        flash(
            "Auto-approve is off. Enable it on the admin dashboard before running batch approve.",
            "error",
        )
        return redirect(url_for("admin.marketers"))
    flash(f"Auto-approved {result['approved']} of {result['considered']} pending marketers.", "success")
    return redirect(url_for("admin.marketers"))


@admin_bp.route("/outcomes/refresh", methods=["POST"])
@require_admin
def refresh_outcomes():
    result = refresh_outcome_scores()
    flash(f"Updated proof scores for {result['updated']} marketers with hire feedback.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/ingest", methods=["POST"])
@require_admin
def ingest():
    try:
        outcome = enqueue(run_discovery_cycle)
        if isinstance(outcome, dict):
            created = outcome.get("created", 0)
            considered = outcome.get("considered", 0)
            serp_used = outcome.get("serpapi_queries_used", 0)
            skipped_known = outcome.get("skipped_known_catalog", 0)
            serp_note = f" Used {serp_used} SerpAPI search(es)." if serp_used else " No SerpAPI searches used."
            if created:
                flash(
                    f"Discovery complete: added {created} new marketer(s) from {considered} fresh candidate(s)."
                    f"{serp_note}",
                    "success",
                )
            elif considered:
                flash(
                    f"Discovery complete: found {considered} new URL(s) to vet; none were added "
                    "(below confidence or not service profiles)."
                    f"{serp_note}",
                    "success",
                )
            else:
                msg = (
                    "Discovery complete: no new URLs found this cycle."
                    f"{serp_note}"
                )
                if skipped_known:
                    msg += f" Skipped {skipped_known} result(s) already in your catalog."
                msg += " Next run will rotate queries and search deeper pages."
                flash(msg, "success")
            return redirect(
                url_for(
                    "admin.marketers",
                    created=created,
                    skipped_existing=outcome.get("skipped_existing", 0),
                    skipped_low_confidence=outcome.get("skipped_low_confidence", 0),
                    skipped_not_profile=outcome.get("skipped_not_profile", 0),
                    skipped_blacklisted=outcome.get("skipped_blacklisted", 0),
                    considered=considered,
                )
            )
        flash(
            "Discovery queued in the background. Refresh this page in a minute to see new marketers.",
            "success",
        )
        return redirect(url_for("admin.marketers", queued=1))
    except Exception as exc:
        flash(f"Discovery failed: {exc}", "error")
        return redirect(url_for("admin.marketers"))


@admin_bp.route("/discovery-report")
@require_admin
def discovery_report():
    report = get_discovery_report()
    return render_template("admin_discovery_report.html", report=report)


@admin_bp.route("/marketers/add", methods=["GET", "POST"])
@require_admin
def add_marketer():
    form = {}
    if request.method == "POST":
        f = request.form
        services = normalize_service_list(f.getlist("services"))
        genres = normalize_genre_list(f.getlist("genres"))
        brand_name = f.get("brand_name", "").strip()
        website = f.get("website", "").strip()
        email = f.get("email", "").strip()
        bio = f.get("bio", "").strip()
        try:
            price_dollars = max(1, int(f.get("price_dollars") or 149))
        except (TypeError, ValueError):
            price_dollars = 149
        try:
            delivery_days = max(1, int(f.get("delivery_days") or 14))
        except (TypeError, ValueError):
            delivery_days = 14
        form = {
            "brand_name": brand_name,
            "website": website,
            "email": email,
            "bio": bio,
            "services": services,
            "genres": genres,
            "price_dollars": price_dollars,
            "delivery_days": delivery_days,
        }
        if not brand_name or not website:
            flash("Brand name and website are required.", "error")
        elif not services:
            flash("Select at least one service.", "error")
        else:
            marketer = provision_platform_marketer(
                brand_name=brand_name,
                website=website,
                email=email,
                bio=bio,
                services=services,
                genres=genres,
                source="admin_manual",
                price_cents=price_dollars * 100,
                delivery_days=delivery_days,
            )
            db.session.commit()
            portal = marketer_portal_url(marketer)
            flash(f"Created {brand_name}. Portal: {portal}", "success")
            return redirect(url_for("admin.marketers"))
    return render_template(
        "admin_add_marketer.html",
        form=form,
        canonical_genres=CANONICAL_GENRES,
        canonical_services=CANONICAL_SERVICES,
    )


@admin_bp.route("/applications")
@require_admin
def applications():
    apps = MarketerApplication.query.order_by(MarketerApplication.created_at.desc()).all()
    approved_brands = {a.brand_name for a in apps if a.status == "approved"}
    marketers_by_brand = {
        m.brand_name: m
        for m in Marketer.query.filter(Marketer.brand_name.in_(approved_brands or [""])).all()
    }
    return render_template(
        "admin_applications.html",
        applications=apps,
        marketers_by_brand=marketers_by_brand,
        stripe_configured=connect_configured(),
        payments_dev_bypass=payments_dev_bypass(),
    )


@admin_bp.route("/applications/<int:id>/approve", methods=["POST"])
@require_admin
def approve_application(id):
    app_row = MarketerApplication.query.get_or_404(id)
    marketer = provision_from_application(app_row)
    app_row.status = "approved"
    db.session.commit()
    portal = marketer_portal_url(marketer)
    flash(f"Approved {app_row.brand_name} with a starter package. Portal: {portal}", "success")
    return redirect(url_for("admin.applications"))


@admin_bp.route("/applications/<int:id>/reject", methods=["POST"])
@require_admin
def reject_application(id):
    app_row = MarketerApplication.query.get_or_404(id)
    app_row.status = "rejected"
    db.session.commit()
    return redirect(url_for("admin.applications"))


@admin_bp.route("/orders")
@require_admin
def orders():
    rows = MarketplaceOrder.query.order_by(MarketplaceOrder.created_at.desc()).limit(100).all()
    marketer_names = {
        m.id: m.brand_name or m.name
        for m in Marketer.query.filter(Marketer.id.in_([r.marketer_id for r in rows] or [0])).all()
    }
    return render_template("admin_orders.html", orders=rows, marketer_names=marketer_names)


@admin_bp.route("/orders/<int:id>/status", methods=["POST"])
@require_admin
def update_order_status(id):
    order = MarketplaceOrder.query.get_or_404(id)
    status = request.form.get("status", "").strip()
    allowed = ("pending_payment", "paid", "in_progress", "delivered", "completed", "cancelled")
    if status in allowed:
        order.status = status
        db.session.commit()
        flash(f"Order #{order.id} marked {status}.", "success")
    return redirect(url_for("admin.orders"))


@admin_bp.route("/intros")
@require_admin
def intros():
    rows = IntroRequest.query.order_by(IntroRequest.created_at.desc()).limit(100).all()
    marketer_names = {
        m.id: m.brand_name or m.name
        for m in Marketer.query.filter(Marketer.id.in_([r.marketer_id for r in rows] or [0])).all()
    }
    return render_template("admin_intros.html", intros=rows, marketer_names=marketer_names)


@admin_bp.route("/intros/<int:id>/status", methods=["POST"])
@require_admin
def update_intro_status(id):
    intro = IntroRequest.query.get_or_404(id)
    status = request.form.get("status", "").strip()
    if status in ("pending", "sent", "replied", "closed"):
        intro.status = status
        db.session.commit()
        flash(f"Intro #{intro.id} marked {status}.", "success")
    return redirect(url_for("admin.intros"))
