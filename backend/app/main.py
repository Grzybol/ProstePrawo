"""FastAPI entry point for the ProstePrawo monolithic backend."""
from fastapi import FastAPI

from .api.routes import documents, health

app = FastAPI(title="ProstePrawo", version="0.1.0")

app.include_router(health.router)
app.include_router(documents.router, prefix="/documents", tags=["documents"])


@app.get("/", tags=["root"])
async def read_root() -> dict[str, str]:
    """Simple root endpoint for smoke-testing deployments."""
    return {"message": "ProstePrawo API is running"}
