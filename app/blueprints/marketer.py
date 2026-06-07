"""Marketer self-serve onboarding blueprint."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.models import MarketerApplication

marketer_bp = Blueprint("marketer", __name__)


@marketer_bp.route("/apply", methods=["GET", "POST"])
def apply():
    if request.method == "POST":
        f = request.form
        application = MarketerApplication(
            brand_name=f.get("brand_name", "").strip(),
            website=f.get("website", "").strip(),
            email=f.get("email", "").strip(),
            bio=f.get("bio", "").strip(),
            services=[s.strip() for s in f.get("services", "").split(",") if s.strip()],
            genres=[g.strip() for g in f.get("genres", "").split(",") if g.strip()],
        )
        if not application.brand_name or not application.website:
            flash("Brand name and website are required.", "error")
            return render_template("marketer_apply.html")
        db.session.add(application)
        db.session.commit()
        return redirect(url_for("marketer.apply_success"))
    return render_template("marketer_apply.html")


@marketer_bp.route("/apply/success")
def apply_success():
    return render_template("marketer_apply_success.html")
