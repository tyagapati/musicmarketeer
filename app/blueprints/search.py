"""Search and browse marketers blueprint."""
from flask import Blueprint, render_template
from app.models import Marketer, CampaignBrief
from app.services.matching import rank_marketers

search_bp = Blueprint("search", __name__)


@search_bp.route("/match/<int:brief_id>")
def match(brief_id):
    brief = CampaignBrief.query.get_or_404(brief_id)
    results = rank_marketers(brief, top_n=5)
    return render_template("search_match.html", brief=brief, results=results)


@search_bp.route("/browse")
def browse():
    marketers = Marketer.query.filter_by(status="approved").limit(50).all()
    return render_template("search_browse.html", marketers=marketers)


@search_bp.route("/marketer/<int:id>")
def marketer_profile(id):
    m = Marketer.query.get_or_404(id)
    return render_template("marketer_profile.html", marketer=m)
