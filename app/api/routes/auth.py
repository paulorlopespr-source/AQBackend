from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.core.security import create_access_token, verify_plain_password
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest):
    settings = get_settings()
    if payload.username != settings.admin_username or not verify_plain_password(
        payload.password,
        settings.admin_password,
    ):
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")

    return TokenResponse(access_token=create_access_token(payload.username))
