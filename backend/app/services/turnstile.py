"""Cloudflare Turnstile verification helpers."""
from __future__ import annotations

import ipaddress
import logging
from typing import Any

import httpx
from fastapi import HTTPException, Request, status

from ..core.config import Settings, get_settings

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
LOGGER = logging.getLogger("prosteprawo.turnstile")


async def require_turnstile(
    token: str | None,
    request: Request,
    *,
    stage: str,
    settings: Settings | None = None,
) -> None:
    """Validate the provided Turnstile token or raise an HTTP error."""

    settings = settings or get_settings()

    if settings.disable_cloudflare_turnstile:
        LOGGER.info(
            "Skipping Turnstile verification (disabled in configuration)",
            extra={"turnstile_stage": stage},
        )
        return

    if not token:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Brak tokenu weryfikacyjnego Turnstile.",
        )

    secret_key = settings.turnstile_secret_key
    if not secret_key:
        LOGGER.error("Turnstile secret key is not configured")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Weryfikacja Turnstile jest obecnie niedostępna.",
        )

    payload: dict[str, Any] = {
        "secret": secret_key,
        "response": token,
    }

    remote_ip = extract_remote_ip(request)
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(TURNSTILE_VERIFY_URL, data=payload)
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPError as exc:  # pragma: no cover - network failure
        log_turnstile_event(stage=stage, success=False, error=str(exc))
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="Błąd połączenia z usługą Turnstile.",
        ) from exc

    success = bool(body.get("success"))
    log_turnstile_event(
        stage=stage,
        success=success,
        request_id=body.get("request_id"),
        data=body,
    )

    if not success:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Weryfikacja Turnstile nie powiodła się.",
        )


def extract_remote_ip(request: Request) -> str | None:
    """Return the most appropriate client IP address for Turnstile."""

    header_order = ["CF-Connecting-IP", "X-Forwarded-For", "X-Real-IP"]
    for header in header_order:
        value = request.headers.get(header)
        if not value:
            continue
        if header == "X-Forwarded-For":
            for candidate in value.split(","):
                normalized = normalize_ip(candidate)
                if normalized and is_public_ip(normalized):
                    return normalized
        else:
            normalized = normalize_ip(value)
            if normalized and is_public_ip(normalized):
                return normalized

    if request.client and request.client.host:
        normalized = normalize_ip(request.client.host)
        if normalized and is_public_ip(normalized):
            return normalized
    return None


def normalize_ip(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip()


def is_public_ip(value: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved)


def log_turnstile_event(
    *,
    stage: str,
    success: bool,
    request_id: str | None = None,
    error: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Log a Turnstile verification attempt for auditing purposes."""

    extra: dict[str, Any] = {
        "turnstile_stage": stage,
        "turnstile_success": success,
        "turnstile_request_id": request_id,
    }
    if error:
        extra["turnstile_error"] = error
    if data:
        extra["turnstile_response"] = data

    if success:
        LOGGER.info("Turnstile verification successful", extra=extra)
    else:
        LOGGER.warning("Turnstile verification failed", extra=extra)
