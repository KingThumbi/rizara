from __future__ import annotations

import os

import requests
from flask import current_app, request


def real_ip() -> str:
    xff = (request.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        return xff.split(",")[0].strip() or "0.0.0.0"
    return request.remote_addr or "0.0.0.0"


def safe_user_agent(maxlen: int = 255) -> str:
    ua = (request.headers.get("User-Agent") or "").strip()
    return ua[:maxlen] if ua else "unknown"


def verify_recaptcha(response_token: str) -> bool:
    secret = (
        current_app.config.get("RECAPTCHA_SECRET_KEY")
        or os.getenv("RECAPTCHA_SECRET_KEY")
        or ""
    ).strip()

    if not secret or not response_token:
        current_app.logger.warning("reCAPTCHA secret/token missing; rejecting request.")
        return False

    try:
        resp = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": secret, "response": response_token},
            timeout=5,
        )
        return bool(resp.json().get("success", False))
    except Exception:
        current_app.logger.exception("reCAPTCHA verification failed.")
        return False