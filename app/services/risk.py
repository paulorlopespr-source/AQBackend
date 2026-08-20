from __future__ import annotations

from math import prod


def analyze_ticket(leg_probabilities: list[int], correlation_factor: float = 1.0) -> dict:
    if not leg_probabilities:
        return {"probability":0,"risk_label":"SEM_SELECOES","message":"Adicione seleções ao bilhete."}
    probabilities=[min(max(p,1),99)/100 for p in leg_probabilities]
    combined=round(prod(probabilities)*max(0.45,min(1.0,correlation_factor))*100)
    combined=min(max(combined,1),99)
    if combined<50:label="ALTO";message="Aposta de alto risco"
    elif combined>=80:label="BAIXO";message="Entrada quantitativamente forte"
    else:label="MODERADO";message="Entrada de risco moderado"
    if correlation_factor<0.999:message += " • correlação entre mercados considerada"
    return {"probability":combined,"risk_label":label,"message":message,"correlation_factor":round(correlation_factor,3)}
