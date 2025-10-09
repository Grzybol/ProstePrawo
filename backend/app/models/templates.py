"""Pydantic models describing document template generation."""
from pydantic import BaseModel, Field

from .documents import DocumentUsageMetrics


class TemplateGenerationRequest(BaseModel):
    """Incoming payload describing the desired template."""

    prompt: str = Field(..., min_length=3, description="Opis celu dokumentu")
    country: str = Field("PL", description="Kod kraju w formacie ISO 3166-1 alpha-2")


class TemplateGenerationResponse(BaseModel):
    """Response returned after generating a template."""

    user_id: int
    country: str
    prompt: str
    template: str
    token_usage: DocumentUsageMetrics = Field(default_factory=DocumentUsageMetrics)
