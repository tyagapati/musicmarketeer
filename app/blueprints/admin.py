"""Admin dashboard blueprint."""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app import db
from app.models import IntroRequest, Marketer, MarketerApplication
from app.services.admin_auth import is_admin_authenticated, require_admin, verify_admin_password
from app.services.discovery_pipeline import get_discovery_report, run_discovery_cycle
from app.services.worker import enqueue

admin_bp = Blueprint("admin", __name__)


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
            return redirect(request.args.get("next") or url_for("admin.index"))
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
    return render_template(
        "admin_index.html",
        pending=pending,
        approved=approved,
        apps_pending=apps_pending,
    )


@admin_bp.route("/marketers")
@require_admin
def marketers():
    result = {
        "created": request.args.get("created", type=int),
        "skipped_existing": request.args.get("skipped_existing", type=int),
        "skipped_low_confidence": request.args.get("skipped_low_confidence", type=int),
        "skipped_not_profile": request.args.get("skipped_not_profile", type=int),
        "considered": request.args.get("considered", type=int),
        "queued": request.args.get("queued", type=int),
    }
    all_marketers = Marketer.query.order_by(Marketer.status).all()
    return render_template("admin_marketers.html", marketers=all_marketers, result=result)


@admin_bp.route("/marketers/<int:id>/approve", methods=["POST"])
@require_admin
def approve(id):
    m = Marketer.query.get_or_404(id)
    m.status = "approved"
    db.session.commit()
    return redirect(url_for("admin.marketers"))


@admin_bp.route("/marketers/<int:id>/reject", methods=["POST"])
@require_admin
def reject(id):
    m = Marketer.query.get_or_404(id)
    m.status = "rejected"
    db.session.commit()
    return redirect(url_for("admin.marketers"))


@admin_bp.route("/marketers/<int:id>/verify-price", methods=["POST"])
@require_admin
def verify_price(id):
    m = Marketer.query.get_or_404(id)
    m.price_verified = True
    db.session.commit()
    return redirect(url_for("admin.marketers"))


@admin_bp.route("/ingest", methods=["POST"])
@require_admin
def ingest():
    outcome = enqueue(run_discovery_cycle)
    if isinstance(outcome, dict):
        return redirect(
            url_for(
                "admin.marketers",
                created=outcome.get("created", 0),
                skipped_existing=outcome.get("skipped_existing", 0),
                skipped_low_confidence=outcome.get("skipped_low_confidence", 0),
                skipped_not_profile=outcome.get("skipped_not_profile", 0),
                considered=outcome.get("considered", 0),
            )
        )
    return redirect(url_for("admin.marketers", queued=1))


@admin_bp.route("/discovery-report")
@require_admin
def discovery_report():
    report = get_discovery_report()
    return render_template("admin_discovery_report.html", report=report)


@admin_bp.route("/applications")
@require_admin
def applications():
    apps = MarketerApplication.query.order_by(MarketerApplication.created_at.desc()).all()
    return render_template("admin_applications.html", applications=apps)


@admin_bp.route("/applications/<int:id>/approve", methods=["POST"])
@require_admin
def approve_application(id):
    app_row = MarketerApplication.query.get_or_404(id)
    marketer = Marketer(
        name=app_row.brand_name,
        brand_name=app_row.brand_name,
        website=app_row.website,
        email=app_row.email,
        bio=app_row.bio,
        genres=app_row.genres or [],
        services=app_row.services or [],
        languages=["en"],
        status="approved",
        source="onboarding",
        price_verified=False,
        affiliate_url=app_row.website,
    )
    app_row.status = "approved"
    db.session.add(marketer)
    db.session.commit()
    return redirect(url_for("admin.applications"))


@admin_bp.route("/applications/<int:id>/reject", methods=["POST"])
@require_admin
def reject_application(id):
    app_row = MarketerApplication.query.get_or_404(id)
    app_row.status = "rejected"
    db.session.commit()
    return redirect(url_for("admin.applications"))


@admin_bp.route("/intros")
@require_admin
def intros():
    rows = IntroRequest.query.order_by(IntroRequest.created_at.desc()).limit(100).all()
    return render_template("admin_intros.html", intros=rows)
