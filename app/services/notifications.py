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
        f"Message:\n{intro.message or '(none)'}\n"
    )
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


def _order_url(order_id: int) -> str:
    return f"{_app_base()}/search/orders/{order_id}"


def notify_match_ready(brief):
    """Email artist a link to their match report after intake."""
    if not brief.email:
        return False
    match_url = _match_url(brief.id)
    subject = "Your SoundMatch matches are ready"
    body = (
        f"Hi {brief.artist_name},\n\n"
        f"We ranked marketers for your campaign. Preview your top matches here:\n"
        f"{match_url}\n\n"
        f"— SoundMatch"
    )
    return send_email(subject, body, [brief.email])


def notify_payment_confirmation(brief):
    """Email artist after successful payment."""
    if not brief.email:
        return False
    match_url = _match_url(brief.id)
    subject = "Your SoundMatch premium match report is ready"
    body = (
        f"Hi {brief.artist_name},\n\n"
        f"Thanks for your purchase. Your full match report and concierge intro credit are unlocked:\n"
        f"{match_url}\n\n"
        f"— SoundMatch"
    )
    return send_email(subject, body, [brief.email])


def notify_order_paid(order):
    """Email artist + marketer when a marketplace order is paid."""
    from app.models import Marketer, MarketerPackage

    marketer = Marketer.query.get(order.marketer_id)
    package = MarketerPackage.query.get(order.package_id)
    pkg_title = package.title if package else "package"
    marketer_name = (marketer.brand_name or marketer.name) if marketer else "your marketer"
    order_url = _order_url(order.id)

    if order.artist_email:
        send_email(
            f"Booking confirmed — {pkg_title}",
            (
                f"Hi {order.artist_name},\n\n"
                f"Your booking with {marketer_name} is confirmed.\n"
                f"Package: {pkg_title}\n"
                f"Track your order: {order_url}\n\n"
                f"— SoundMatch"
            ),
            [order.artist_email],
        )

    recipients = []
    if marketer and marketer.email:
        recipients.append(marketer.email)
    admin_to = _smtp_settings()["admin_to"]
    if admin_to:
        recipients.append(admin_to)
    if recipients:
        send_email(
            f"New SoundMatch booking from {order.artist_name}",
            (
                f"Artist: {order.artist_name} ({order.artist_email})\n"
                f"Package: {pkg_title}\n"
                f"Order: #{order.id}\n"
                f"Amount: ${(order.amount_cents or 0) / 100:.2f}\n\n"
                f"Mark delivered in your marketer portal when work is done.\n"
            ),
            recipients,
        )
    return True


def notify_order_delivered(order):
    """Email artist when marketer marks order delivered."""
    if not order.artist_email:
        return False
    send_email(
        f"Your marketer delivered order #{order.id}",
        (
            f"Hi {order.artist_name},\n\n"
            f"Your SoundMatch booking was marked delivered. Review and confirm completion:\n"
            f"{_order_url(order.id)}\n\n"
            f"— SoundMatch"
        ),
        [order.artist_email],
    )
    return True


def notify_order_completed(order):
    """Email marketer when artist confirms order complete."""
    from app.models import Marketer

    marketer = Marketer.query.get(order.marketer_id)
    if not marketer or not marketer.email:
        return False
    send_email(
        f"Order #{order.id} marked complete",
        (
            f"Hi {marketer.brand_name or marketer.name},\n\n"
            f"The artist confirmed order #{order.id} is complete.\n"
            f"Payout will process per your Stripe Connect settings.\n\n"
            f"— SoundMatch"
        ),
        [marketer.email],
    )
    return True


def notify_concierge_intro(intro, marketer, brief):
    """Alert admin to send a concierge intro on the artist's behalf."""
    admin_to = _smtp_settings()["admin_to"]
    if not admin_to:
        logger.info(
            "Concierge intro queued (admin email unset): artist=%s marketer=%s brief=%s",
            intro.artist_name,
            marketer.brand_name or marketer.name,
            brief.id if brief else None,
        )
        return True
    subject = f"[Action needed] Concierge intro: {intro.artist_name} → {marketer.brand_name or marketer.name}"
    body = (
        f"Artist: {intro.artist_name} ({intro.email})\n"
        f"Marketer: {marketer.brand_name or marketer.name}\n"
        f"Brief ID: {brief.id if brief else 'n/a'}\n"
        f"Marketer email: {marketer.email or 'unknown'}\n"
        f"Message:\n{intro.message or '(none)'}\n\n"
        f"Send the warm intro from SoundMatch and mark status sent in admin.\n"
    )
    return send_email(subject, body, [admin_to])
