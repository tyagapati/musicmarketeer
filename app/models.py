"""SQLAlchemy models."""
import json
from datetime import datetime

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


class JsonDict(db.TypeDecorator):
    impl = db.Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return "{}"
        return json.dumps(value if isinstance(value, dict) else dict(value))

    def process_result_value(self, value, dialect):
        if not value:
            return {}
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return {}


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
    price_verified = db.Column(db.Boolean, default=False)
    price_source = db.Column(db.String(50), default="estimated")
    affiliate_url = db.Column(db.String(500))
    booking_url = db.Column(db.String(500))
    portal_token = db.Column(db.String(128), unique=True)
    domain_key = db.Column(db.String(255), index=True)
    preferred_maturity = db.Column(JsonList, default=list)
    portfolio_urls = db.Column(JsonList, default=list)
    evidence_summary = db.Column(db.Text)
    proof_strength = db.Column(db.Integer)
    source = db.Column(db.String(50))
    status = db.Column(db.String(50), default="pending")
    confidence_score = db.Column(db.Integer)
    provider_type = db.Column(db.String(20), default="agency")
    enrolled = db.Column(db.Boolean, default=False)
    stripe_connect_account_id = db.Column(db.String(255))
    payouts_enabled = db.Column(db.Boolean, default=False)

    packages = db.relationship("MarketerPackage", backref="marketer", lazy="dynamic")
    orders = db.relationship("MarketplaceOrder", backref="marketer", lazy="dynamic")


class MarketerPackage(db.Model):
    __tablename__ = "marketer_packages"
    id = db.Column(db.Integer, primary_key=True)
    marketer_id = db.Column(db.Integer, db.ForeignKey("marketers.id"), nullable=False, index=True)
    service = db.Column(db.String(80), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    price_cents = db.Column(db.Integer, nullable=False)
    delivery_days = db.Column(db.Integer, default=7)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MarketplaceOrder(db.Model):
    __tablename__ = "marketplace_orders"
    id = db.Column(db.Integer, primary_key=True)
    brief_id = db.Column(db.Integer, db.ForeignKey("campaign_briefs.id"), nullable=True)
    marketer_id = db.Column(db.Integer, db.ForeignKey("marketers.id"), nullable=False)
    package_id = db.Column(db.Integer, db.ForeignKey("marketer_packages.id"), nullable=False)
    artist_name = db.Column(db.String(255), nullable=False)
    artist_email = db.Column(db.String(255), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    platform_fee_cents = db.Column(db.Integer, default=0)
    marketer_payout_cents = db.Column(db.Integer, default=0)
    status = db.Column(db.String(50), default="pending_payment")
    stripe_checkout_session_id = db.Column(db.String(255))
    stripe_payment_intent_id = db.Column(db.String(255))
    stripe_transfer_id = db.Column(db.String(255))
    paid_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    rating = db.Column(db.Integer)
    review_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    brief = db.relationship("CampaignBrief", backref="orders")
    package = db.relationship("MarketerPackage", backref="orders")


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
    payment_status = db.Column(db.String(50), default="unpaid")
    paid_at = db.Column(db.DateTime)
    stripe_checkout_session_id = db.Column(db.String(255))
    concierge_intros_remaining = db.Column(db.Integer, default=0)

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


class IntroRequest(db.Model):
    __tablename__ = "intro_requests"
    id = db.Column(db.Integer, primary_key=True)
    marketer_id = db.Column(db.Integer, db.ForeignKey("marketers.id"), nullable=False)
    artist_name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text)
    brief_id = db.Column(db.Integer, db.ForeignKey("campaign_briefs.id"), nullable=True)
    intro_type = db.Column(db.String(50), default="self_serve")
    status = db.Column(db.String(50), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    brief = db.relationship("CampaignBrief", backref="intro_requests")


class MarketerApplication(db.Model):
    __tablename__ = "marketer_applications"
    id = db.Column(db.Integer, primary_key=True)
    brand_name = db.Column(db.String(255), nullable=False)
    website = db.Column(db.String(500), nullable=False)
    email = db.Column(db.String(255))
    services = db.Column(JsonList, default=list)
    genres = db.Column(JsonList, default=list)
    bio = db.Column(db.Text)
    status = db.Column(db.String(50), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MatchFeedback(db.Model):
    __tablename__ = "match_feedback"
    id = db.Column(db.Integer, primary_key=True)
    brief_id = db.Column(db.Integer, db.ForeignKey("campaign_briefs.id"), nullable=False)
    marketer_id = db.Column(db.Integer, db.ForeignKey("marketers.id"), nullable=False)
    hired = db.Column(db.Boolean, default=False)
    rating = db.Column(db.Integer)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AppSetting(db.Model):
    __tablename__ = "app_settings"
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=False, default="false")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VerificationDecision(db.Model):
    __tablename__ = "verification_decisions"
    id = db.Column(db.Integer, primary_key=True)
    marketer_id = db.Column(db.Integer, db.ForeignKey("marketers.id"), nullable=True)
    url = db.Column(db.String(500))
    decision = db.Column(db.String(50), nullable=False, default="pending")
    reason_codes = db.Column(JsonList, default=list)
    scores = db.Column(JsonDict, default=dict)
    evidence_summary = db.Column(db.Text)
    llm_raw_response = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    marketer = db.relationship("Marketer", backref="verification_decisions")


class RejectedSite(db.Model):
    __tablename__ = "rejected_sites"
    id = db.Column(db.Integer, primary_key=True)
    domain_key = db.Column(db.String(255), unique=True, nullable=False, index=True)
    website = db.Column(db.String(500))
    brand_name = db.Column(db.String(255))
    reason = db.Column(db.String(100), default="admin_reject")
    notes = db.Column(db.Text)
    rejected_at = db.Column(db.DateTime, default=datetime.utcnow)
