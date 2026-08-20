from __future__ import annotations

import json

import httpx

from app.core.config import get_settings


class AiService:
    """IA interpreta o cálculo quantitativo do AQ sem inventar estatísticas."""

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
        return await self._request_structured(ticket_context, task="ticket")

    async def analyze_match(self, match_context: dict) -> dict:
        # Sempre existe um fallback quantitativo para o card funcionar mesmo sem IA.
        markets = sorted(
            match_context.get("market_probabilities", []),
            key=lambda x: (x.get("probability", 0), x.get("data_confidence", 0)),
            reverse=True,
        )
        consistent = [
            m for m in markets
            if m.get("probability", 0) >= 68 and m.get("data_confidence", 0) >= 60
        ][:3]

        fallback = {
            "configured": False,
            "headline": "Leitura quantitativa AQ",
            "summary": match_context.get("summary", "Análise baseada nos últimos jogos disponíveis."),
            "recommended_entries": [
                {
                    "market": m.get("market", ""),
                    "selection": m.get("selection", ""),
                    "probability": int(m.get("probability", 0)),
                    "confidence": int(m.get("data_confidence", 0)),
                    "risk": m.get("risk", "ALTO"),
                    "reason": m.get("rationale", "Sinal gerado pelo modelo quantitativo AQ."),
                    "verdict": "CONSISTENTE" if m.get("risk") != "ALTO" else "CAUTELA",
                }
                for m in consistent
            ],
            "avoid": [
                f"{m.get('market', '')} • {m.get('selection', '')}"
                for m in markets
                if m.get("risk") == "ALTO"
            ][:2],
            "ai_note": "IA não configurada; recomendações derivadas somente do motor quantitativo.",
        }

        if not self.configured:
            return fallback

        try:
            result = await self._request_structured(match_context, task="match")
            result["configured"] = True
            return result
        except Exception:
            fallback["ai_note"] = "IA temporariamente indisponível; exibindo análise quantitativa de contingência."
            return fallback

    async def _request_structured(self, context: dict, task: str) -> dict:
        if task == "match":
            schema = {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "summary": {"type": "string"},
                    "recommended_entries": {
                        "type": "array",
                        "maxItems": 3,
                        "items": {
                            "type": "object",
                            "properties": {
                                "market": {"type": "string"},
                                "selection": {"type": "string"},
                                "probability": {"type": "integer"},
                                "confidence": {"type": "integer"},
                                "risk": {"type": "string"},
                                "reason": {"type": "string"},
                                "verdict": {"type": "string"},
                            },
                            "required": ["market", "selection", "probability", "confidence", "risk", "reason", "verdict"],
                            "additionalProperties": False,
                        },
                    },
                    "avoid": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
                    "ai_note": {"type": "string"},
                },
                "required": ["headline", "summary", "recommended_entries", "avoid", "ai_note"],
                "additionalProperties": False,
            }
            instructions = (
                "Você é a camada interpretativa do AQ, um assistente quantitativo de apostas. "
                "Use SOMENTE os dados recebidos. Não invente estatísticas, odds, notícias, escalações ou probabilidades. "
                "A probabilidade e a confiança fornecidas pelo motor quantitativo são a base e não podem ser aumentadas pela IA. "
                "Escolha no máximo 3 entradas mais consistentes, priorizando alta confiança, risco baixo/moderado, EV positivo quando existir, "
                "e coerência entre últimos jogos, gols, escanteios e finalizações. Se não houver entrada suficientemente consistente, retorne lista vazia. "
                "Explique de forma curta e objetiva em português do Brasil."
            )
        else:
            schema = {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
                "additionalProperties": False,
            }
            instructions = "Interprete o contexto quantitativo fornecido sem inventar dados."

        payload = {
            "model": "gpt-5.6-luna",
            "instructions": instructions,
            "input": json.dumps(context, ensure_ascii=False),
            "text": {
                "verbosity": "low",
                "format": {
                    "type": "json_schema",
                    "name": f"aq_{task}_analysis",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=35) as client:
            response = await client.post("https://api.openai.com/v1/responses", headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()

        text = ""
        for item in body.get("output", []):
            if item.get("type") != "message":
                continue
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    text += part.get("text", "")
        if not text:
            raise RuntimeError("Resposta da IA sem conteúdo estruturado")
        return json.loads(text)
