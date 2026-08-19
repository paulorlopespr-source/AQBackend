from app.core.config import get_settings


class AiService:
    """
    Adaptador preparado para IA.

    Regra do AQ:
    1) estatísticas e motor quantitativo calculam probabilidades;
    2) a IA interpreta risco, correlação e contexto;
    3) a IA não inventa estatísticas nem substitui o cálculo-base.
    """

    def __init__(self):
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.openai_api_key)

    async def explain_ticket(self, ticket_context: dict) -> dict:
        if not self.configured:
            return {
                "configured": False,
                "message": "OPENAI_API_KEY ainda não configurada no backend.",
            }

        # Integração real com o provedor de IA entra na próxima versão.
        # A chave já está isolada no backend e nunca será enviada ao APK.
        return {
            "configured": True,
            "message": "Camada de IA configurada; cliente remoto ainda não habilitado nesta versão.",
        }
