"""FastAPI entry point for the ProstePrawo monolithic backend."""

from __future__ import annotations

from pathlib import Path


def _discover_project_root(start_path: Path | None = None) -> Path:
    """Return the repository root that contains the built frontend assets."""

    current = (start_path or Path(__file__).resolve())
    if current.is_file():
        current = current.parent

    for directory in [current, *current.parents]:
        if (directory / "frontend" / "dist").exists():
            return directory.resolve()

    return Path(__file__).resolve().parents[2]

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.routes import documents, health


BASE_DIR = _discover_project_root()
FRONTEND_DIST_DIR = (BASE_DIR / "frontend" / "dist").resolve()
INDEX_FILE = FRONTEND_DIST_DIR / "index.html"


class SPAStaticFiles(StaticFiles):
    """Static file handler that falls back to ``index.html`` for SPA routes."""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and INDEX_FILE.exists():
                return await super().get_response("index.html", scope)
            raise


app = FastAPI(title="ProstePrawo", version="0.1.0")

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(api_router)


@app.get("/", include_in_schema=False)
async def serve_frontend_root() -> FileResponse:
    """Return the compiled frontend entry point."""

    if not INDEX_FILE.exists():
        raise HTTPException(status_code=503, detail="Frontend build not found")
    return FileResponse(INDEX_FILE)


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend_spa(full_path: str) -> FileResponse:
    """Serve static assets or fall back to ``index.html`` for SPA routes."""

    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    candidate = (FRONTEND_DIST_DIR / full_path).resolve()
    if candidate.is_file() and FRONTEND_DIST_DIR in candidate.parents:
        return FileResponse(candidate)
    if not INDEX_FILE.exists():
        raise HTTPException(status_code=503, detail="Frontend build not found")
    return FileResponse(INDEX_FILE)


if FRONTEND_DIST_DIR.exists():
    app.mount("/", SPAStaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")
