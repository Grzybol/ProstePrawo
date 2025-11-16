"""Endpoints for generating legal document templates."""
from fastapi import APIRouter, Depends, HTTPException

from ...api.deps import get_current_user
from ...models.auth import User
from ...models.templates import TemplateGenerationRequest, TemplateGenerationResponse
from ...services import inference

router = APIRouter()


@router.post(
    "/",
    summary="Generate a legal document template",
    response_model=TemplateGenerationResponse,
)
async def create_template(
    payload: TemplateGenerationRequest,
    current_user: User = Depends(get_current_user),
) -> TemplateGenerationResponse:
    """Produce a structured template tailored to the selected country."""

    try:
        template, usage = inference.generate_document_template(payload.prompt, payload.country)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return TemplateGenerationResponse(
        user_id=current_user.id,
        country=payload.country.strip().upper() or "PL",
        prompt=payload.prompt.strip(),
        template=template,
        token_usage=usage,
    )
