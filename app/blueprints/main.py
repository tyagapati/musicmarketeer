"""Home page blueprint."""
from flask import Blueprint, jsonify, render_template

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    return render_template("index.html")


@main_bp.route("/health")
def health():
    payload = {"status": "ok"}
    from flask import request

    if request.args.get("spotify") == "1":
        from app.services.spotify_client import spotify_configured, verify_spotify_credentials

        payload["spotify_configured"] = spotify_configured()
        if spotify_configured():
            payload["spotify"] = verify_spotify_credentials()
    return jsonify(payload)


@main_bp.route("/terms")
def terms():
    return render_template("terms.html")


@main_bp.route("/privacy")
def privacy():
    return render_template("privacy.html")
