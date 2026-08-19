from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from app.core.config import get_settings
from app.core.security import create_access_token, verify_plain_password
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _authenticate(username: str, password: str) -> TokenResponse:
    settings = get_settings()
    if username != settings.admin_username or not verify_plain_password(
        password,
        settings.admin_password,
    ):
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")

    return TokenResponse(access_token=create_access_token(username))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest):
    # Endpoint JSON usado pelo aplicativo Android.
    return _authenticate(payload.username, payload.password)


@router.post("/token", response_model=TokenResponse)
def token(form_data: OAuth2PasswordRequestForm = Depends()):
    # Endpoint padrão OAuth2 usado pelo botão Authorize do Swagger.
    return _authenticate(form_data.username, form_data.password)
