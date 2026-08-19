from __future__ import annotations

from math import prod


def analyze_ticket(leg_probabilities: list[int]) -> dict:
    if not leg_probabilities:
        return {
            "probability": 0,
            "risk_label": "SEM_SELECOES",
            "message": "Adicione seleções ao bilhete.",
        }

    probabilities = [min(max(p, 1), 99) / 100 for p in leg_probabilities]
    # Para múltiplas, a probabilidade conjunta é multiplicativa.
    # É deliberadamente conservadora e não é promessa de resultado.
    combined = round(prod(probabilities) * 100)
    combined = min(max(combined, 1), 99)

    if combined < 50:
        label = "ALTO"
        message = "Aposta de alto risco"
    elif combined >= 80:
        label = "BAIXO"
        message = "Boa entrada, boa sorte!"
    else:
        label = "MODERADO"
        message = "Entrada de risco moderado"

    return {
        "probability": combined,
        "risk_label": label,
        "message": message,
    }
