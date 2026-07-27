"""Email notifications (SMTP optional; logs when not configured)."""
import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def _smtp_settings():
    return {
        "host": os.environ.get("SMTP_HOST", "").strip(),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER", "").strip(),
        "password": os.environ.get("SMTP_PASSWORD", "").strip(),
        "from_addr": os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", "")).strip(),
        "admin_to": os.environ.get("ADMIN_NOTIFY_EMAIL", "").strip(),
    }


def send_email(subject, body, to_addrs):
    cfg = _smtp_settings()
    recipients = [a.strip() for a in to_addrs if a and a.strip()]
    if not recipients:
        return False

    if not cfg["host"]:
        logger.info("Email (not sent — SMTP_HOST unset): to=%s subject=%s\n%s", recipients, subject, body)
        return True

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"] or cfg["user"]
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
        if cfg["user"]:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
        server.send_message(msg)
    return True


def notify_intro_request(intro, marketer):
    """Notify marketer and admin when an artist requests an intro."""
    intro_label = "Concierge intro" if intro.intro_type == "concierge" else "Intro request"
    subject = f"SoundMatch {intro_label} for {marketer.brand_name or marketer.name}"
    body = (
        f"Type: {intro.intro_type}\n"
        f"Status: {intro.status}\n"
        f"Artist: {intro.artist_name}\n"
        f"Artist email: {intro.email}\n"
        f"Marketer: {marketer.brand_name or marketer.name}\n"
    )
    if intro.brief_id:
        body += f"Campaign report: {_report_url(intro.brief_id)}\n"
        body += f"Match page: {_match_url(intro.brief_id)}\n"
    body += f"Message:\n{intro.message or '(none)'}\n"
    recipients = []
    if intro.intro_type == "self_serve" and marketer.email:
        recipients.append(marketer.email)
    admin_to = _smtp_settings()["admin_to"]
    if admin_to:
        recipients.append(admin_to)
    send_email(subject, body, recipients)


def _app_base() -> str:
    return os.environ.get("APP_URL", "http://127.0.0.1:8000").rstrip("/")


def _match_url(brief_id: int) -> str:
    return f"{_app_base()}/search/match/{brief_id}"


def _report_url(brief_id: int) -> str:
    return f"{_app_base()}/artist/campaign/{brief_id}/report"


def notify_match_ready(brief):
    """Email artist a link to their campaign report after intake."""
    if not brief.email:
        return False
    report_url = _report_url(brief.id)
    match_url = _match_url(brief.id)
    subject = "Your SoundMatch campaign report is ready"
    body = (
        f"Hi {brief.artist_name},\n\n"
        f"Your music analysis, marketing strategy, and top marketer matches are ready:\n"
        f"{report_url}\n\n"
        f"Request introductions to marketers here:\n"
        f"{match_url}\n\n"
        f"— SoundMatch"
    )
    return send_email(subject, body, [brief.email])


def notify_match_feedback(feedback, brief):
    """Log artist outcome feedback for ranking improvements."""
    cfg = _smtp_settings()
    if not cfg["admin_to"]:
        logger.info(
            "Match feedback brief=%s marketer=%s hired=%s rating=%s",
            feedback.brief_id,
            feedback.marketer_id,
            feedback.hired,
            feedback.rating,
        )
        return False
    subject = f"SoundMatch match feedback — {brief.artist_name}"
    body = (
        f"Artist: {brief.artist_name}\n"
        f"Brief: #{brief.id}\n"
        f"Marketer ID: {feedback.marketer_id}\n"
        f"Hired: {feedback.hired}\n"
        f"Rating: {feedback.rating or 'n/a'}\n"
        f"Notes: {feedback.notes or '(none)'}\n"
    )
    return send_email(subject, body, [cfg["admin_to"]])
