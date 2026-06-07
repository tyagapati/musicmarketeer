"""Simple admin authentication for /admin routes."""
import os
from functools import wraps

from flask import redirect, request, session, url_for


def admin_password():
    return os.environ.get("ADMIN_PASSWORD", "").strip()


def is_admin_authenticated():
    if not admin_password():
        return True
    return session.get("admin_authenticated") is True


def verify_admin_password(password):
    expected = admin_password()
    if not expected:
        return True
    return (password or "").strip() == expected


def verify_cron_secret():
    secret = os.environ.get("DISCOVERY_CRON_SECRET", "").strip()
    if not secret:
        return False
    return request.headers.get("X-Cron-Secret", "") == secret


def require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if is_admin_authenticated() or verify_cron_secret():
            return view(*args, **kwargs)
        return redirect(url_for("admin.login", next=request.path))

    return wrapped
