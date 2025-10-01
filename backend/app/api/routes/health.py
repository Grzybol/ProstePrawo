"""Health and status endpoints."""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", summary="Readiness probe")
async def get_health() -> dict[str, str]:
    """Return a simple heartbeat payload for uptime checks."""
    return {"status": "ok"}
