from fastapi import APIRouter

from app.config import settings
from app.ai.verify_keys import verify_all_keys

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/ai")
async def ai_health_check():
    """Check that external AI service API keys are valid."""
    results = await verify_all_keys(
        settings.anthropic_api_key,
        settings.openai_api_key,
        settings.google_api_key,
        settings.voyage_ai_key,
    )
    return results
