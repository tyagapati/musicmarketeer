"""SQLAlchemy models."""
import json
from app import db


class JsonList(db.TypeDecorator):
    impl = db.Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return "[]"
        return json.dumps(value if isinstance(value, list) else list(value))

    def process_result_value(self, value, dialect):
        if not value:
            return []
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return []


class Marketer(db.Model):
    __tablename__ = "marketers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    brand_name = db.Column(db.String(255))
    website = db.Column(db.String(500))
    email = db.Column(db.String(255))
    bio = db.Column(db.Text)
    genres = db.Column(JsonList, default=list)
    services = db.Column(JsonList, default=list)
    languages = db.Column(JsonList, default=list)
    timezone = db.Column(db.String(100))
    geography = db.Column(db.String(100))
    price_min = db.Column(db.Integer)
    price_max = db.Column(db.Integer)
    price_model = db.Column(db.String(50))
    preferred_maturity = db.Column(JsonList, default=list)
    portfolio_urls = db.Column(JsonList, default=list)
    evidence_summary = db.Column(db.Text)
    proof_strength = db.Column(db.Integer)
    source = db.Column(db.String(50))
    status = db.Column(db.String(50), default="pending")
    confidence_score = db.Column(db.Integer)


class CampaignBrief(db.Model):
    __tablename__ = "campaign_briefs"
    id = db.Column(db.Integer, primary_key=True)
    artist_name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255))
    genres = db.Column(JsonList, default=list)
    sub_genres = db.Column(JsonList, default=list)
    goals = db.Column(JsonList, default=list)
    services_needed = db.Column(JsonList, default=list)
    budget_min = db.Column(db.Integer)
    budget_max = db.Column(db.Integer)
    spotify_monthly_listeners = db.Column(db.Integer, default=0)
    tiktok_followers = db.Column(db.Integer, default=0)
    ig_followers = db.Column(db.Integer, default=0)
    yt_subscribers = db.Column(db.Integer, default=0)
    timezone = db.Column(db.String(100))
    languages = db.Column(JsonList, default=list)
    timeline = db.Column(db.String(100))
    past_marketing_exp = db.Column(db.String(100))
    maturity_tier = db.Column(db.String(50))

    def compute_maturity(self):
        total = (
            (self.spotify_monthly_listeners or 0)
            + (self.tiktok_followers or 0)
            + (self.ig_followers or 0)
            + (self.yt_subscribers or 0) * 10
        )
        if total < 5000:
            self.maturity_tier = "early"
        elif total < 50000:
            self.maturity_tier = "mid"
        else:
            self.maturity_tier = "advanced"
