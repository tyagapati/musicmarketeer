"""Admin dashboard blueprint."""
from flask import Blueprint, render_template, redirect, request, url_for
from app import db
from app.models import Marketer
from app.services.discovery_pipeline import run_discovery_cycle
from app.services.worker import enqueue

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/")
def index():
    pending = Marketer.query.filter_by(status="pending").count()
    approved = Marketer.query.filter_by(status="approved").count()
    return render_template("admin_index.html", pending=pending, approved=approved)


@admin_bp.route("/marketers")
def marketers():
    result = {
        "created": request.args.get("created", type=int),
        "skipped_existing": request.args.get("skipped_existing", type=int),
        "skipped_low_confidence": request.args.get("skipped_low_confidence", type=int),
        "considered": request.args.get("considered", type=int),
        "queued": request.args.get("queued", type=int),
    }
    all_marketers = Marketer.query.order_by(Marketer.status).all()
    return render_template("admin_marketers.html", marketers=all_marketers, result=result)


@admin_bp.route("/marketers/<int:id>/approve", methods=["POST"])
def approve(id):
    m = Marketer.query.get_or_404(id)
    m.status = "approved"
    db.session.commit()
    return redirect(url_for("admin.marketers"))


@admin_bp.route("/marketers/<int:id>/reject", methods=["POST"])
def reject(id):
    m = Marketer.query.get_or_404(id)
    m.status = "rejected"
    db.session.commit()
    return redirect(url_for("admin.marketers"))


@admin_bp.route("/ingest", methods=["POST"])
def ingest():
    outcome = enqueue(run_discovery_cycle)
    if isinstance(outcome, dict):
        return redirect(
            url_for(
                "admin.marketers",
                created=outcome.get("created", 0),
                skipped_existing=outcome.get("skipped_existing", 0),
                skipped_low_confidence=outcome.get("skipped_low_confidence", 0),
                considered=outcome.get("considered", 0),
            )
        )
    return redirect(url_for("admin.marketers", queued=1))
