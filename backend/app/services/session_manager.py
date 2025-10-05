"""Session token helper used to issue and validate login cookies."""
from __future__ import annotations

from itsdangerous import BadSignature, BadTimeSignature, URLSafeTimedSerializer


SESSION_COOKIE_NAME = "prosteprawo_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7


class SessionManager:
    """Serialize and verify session payloads using a shared secret."""

    def __init__(self, secret_key: str, *, max_age_seconds: int = SESSION_MAX_AGE) -> None:
        self.serializer = URLSafeTimedSerializer(secret_key=secret_key, salt="prosteprawo-session")
        self.max_age_seconds = max_age_seconds

    def create(self, user_id: int) -> str:
        """Return a signed session token for the provided user identifier."""

        return self.serializer.dumps({"user_id": int(user_id)})

    def verify(self, token: str) -> int | None:
        """Validate the provided token and return the encoded user identifier."""

        try:
            payload = self.serializer.loads(token, max_age=self.max_age_seconds)
        except (BadSignature, BadTimeSignature):
            return None
        user_id = payload.get("user_id")
        if user_id is None:
            return None
        return int(user_id)
