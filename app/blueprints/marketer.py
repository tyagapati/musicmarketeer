"""Marketer applications and profile portal."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.constants.marketer_taxonomy import (
    CANONICAL_GENRES,
    CANONICAL_SERVICES,
    normalize_genre_list,
    normalize_service_list,
)
from app.models import Marketer, MarketerApplication

marketer_bp = Blueprint("marketer", __name__)


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
    marketer = Marketer.query.filter_by(portal_token=token, status="approved").first_or_404()
    if request.method == "POST":
        marketer.bio = request.form.get("bio", "").strip()
        marketer.email = request.form.get("email", "").strip()
        marketer.services = normalize_service_list(request.form.getlist("services")) or marketer.services
        marketer.genres = normalize_genre_list(request.form.getlist("genres")) or marketer.genres
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("marketer.portal", token=token))

    return render_template(
        "marketer_portal.html",
        marketer=marketer,
        canonical_genres=CANONICAL_GENRES,
        canonical_services=CANONICAL_SERVICES,
    )
