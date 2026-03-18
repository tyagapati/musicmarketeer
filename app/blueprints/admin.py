"""Admin dashboard blueprint."""
from flask import Blueprint, render_template, request, redirect, url_for
from app import db
from app.models import Marketer

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/")
def index():
    pending = Marketer.query.filter_by(status="pending").count()
    approved = Marketer.query.filter_by(status="approved").count()
    return render_template("admin_index.html", pending=pending, approved=approved)


@admin_bp.route("/marketers")
def marketers():
    all_marketers = Marketer.query.order_by(Marketer.status).all()
    return render_template("admin_marketers.html", marketers=all_marketers)


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
