from fastapi import APIRouter, Depends

from app.core.security import current_user
from app.services.ai import AiService

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(current_user)])


@router.get("/status")
def ai_status():
    service = AiService()
    return {
        "configured": service.configured,
        "policy": "IA interpreta resultados quantitativos; não inventa a probabilidade-base.",
    }
