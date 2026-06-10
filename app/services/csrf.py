"""Lightweight CSRF protection for HTML form POSTs."""
from __future__ import annotations

import secrets

from flask import abort, current_app, request, session

EXEMPT_ENDPOINTS = frozenset(
    {
        "search.stripe_webhook",
    }
)


def get_csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def validate_csrf() -> None:
    if current_app.config.get("TESTING"):
        return
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    if request.endpoint in EXEMPT_ENDPOINTS:
        return
    submitted = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
    expected = session.get("csrf_token")
    if not expected or not submitted or not secrets.compare_digest(submitted, expected):
        abort(400, description="Invalid or missing CSRF token")
