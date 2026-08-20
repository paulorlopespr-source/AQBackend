from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import prod
from typing import Any


MODEL_VERSION = "AQ Model 1.0"

LEAGUE_PROFILES = {
    "serie a": {"goal": 0.98, "corner": 1.00, "confidence": 1.00},
    "brasileir": {"goal": 0.98, "corner": 1.00, "confidence": 1.00},
    "serie b": {"goal": 0.94, "corner": 0.98, "confidence": 0.98},
    "eredivisie": {"goal": 1.08, "corner": 1.02, "confidence": 1.00},
    "eliteserien": {"goal": 1.05, "corner": 1.02, "confidence": 0.99},
    "libertadores": {"goal": 0.96, "corner": 0.99, "confidence": 0.98},
}


def league_profile(league: str) -> dict[str, float]:
    text = league.lower()
    for key, profile in LEAGUE_PROFILES.items():
        if key in text:
            return profile
    return {"goal": 1.0, "corner": 1.0, "confidence": 0.97}


def probability_class(probability: int) -> str:
    if probability >= 80:
        return "FORTE"
    if probability >= 70:
        return "CONSISTENTE"
    if probability >= 60:
        return "CAUTELA"
    return "EVITAR"


def risk_score(risk: str) -> int:
    return {"BAIXO": 3, "MODERADO": 2, "ALTO": 1}.get(risk.upper(), 1)


def opportunity_score(item: dict[str, Any]) -> float:
    probability = float(item.get("probability") or 0)
    confidence = float(item.get("data_confidence") or item.get("confidence") or 0)
    ev = float(item.get("ev_percent") or 0)
    risk = risk_score(str(item.get("risk") or "ALTO"))
    value_bonus = 8 if str(item.get("value_label", "")).upper() == "VALUE FORTE" else 4 if "VALUE" in str(item.get("value_label", "")).upper() else 0
    return round(probability * 0.42 + confidence * 0.28 + max(-20.0, min(30.0, ev)) * 0.18 + risk * 3 + value_bonus, 2)


def correlation_group(market: str, selection: str) -> str:
    text = f"{market} {selection}".lower()
    if "goal" in text or "gols" in text or "btts" in text or "ambas" in text:
        return "GOALS"
    if "corner" in text or "escante" in text or "canto" in text:
        return "CORNERS"
    if "double" in text or "dupla" in text or "resultado" in text:
        return "RESULT"
    return "OTHER"


def correlation_penalty(existing: list[dict[str, Any]], candidate: dict[str, Any]) -> tuple[float, str]:
    fixture = str(candidate.get("fixture_id") or "")
    group = correlation_group(str(candidate.get("market") or ""), str(candidate.get("selection") or ""))
    same = [x for x in existing if str(x.get("fixture_id") or "") == fixture and correlation_group(str(x.get("market") or ""), str(x.get("selection") or "")) == group]
    if not same:
        return 1.0, "Sem correlação relevante detectada."
    return max(0.45, 1.0 - 0.18 * len(same)), f"Exposição correlacionada no mesmo jogo/mercado ({len(same)} seleção(ões) semelhante(s))."


def dynamic_stake(
    bankroll: float,
    unit_percent: float,
    max_stake_percent: float,
    probability: int,
    confidence: int,
    ev_percent: float | None,
    risk: str,
    drawdown_percent: float,
    red_streak: int,
    current_exposure_percent: float,
    correlation_factor: float = 1.0,
) -> dict[str, Any]:
    if bankroll <= 0:
        return {"stake": 0.0, "percent": 0.0, "reason": "Banca sem saldo."}
    base_percent = max(0.1, unit_percent)
    probability_factor = max(0.55, min(1.15, probability / 80.0))
    confidence_factor = max(0.50, min(1.10, confidence / 80.0))
    ev_factor = 1.0 if ev_percent is None else max(0.60, min(1.20, 1.0 + ev_percent / 100.0))
    risk_factor = {"BAIXO": 1.0, "MODERADO": 0.80, "ALTO": 0.50}.get(risk.upper(), 0.50)
    drawdown_factor = 1.0 if drawdown_percent <= 3 else 0.80 if drawdown_percent <= 7 else 0.60
    streak_factor = 1.0 if red_streak < 2 else 0.80 if red_streak == 2 else 0.60
    exposure_factor = 1.0 if current_exposure_percent < 1.5 else 0.75 if current_exposure_percent < 2.5 else 0.50
    suggested_percent = base_percent * probability_factor * confidence_factor * ev_factor * risk_factor * drawdown_factor * streak_factor * exposure_factor * correlation_factor
    suggested_percent = max(0.0, min(max_stake_percent, suggested_percent))
    return {
        "stake": round(bankroll * suggested_percent / 100.0, 2),
        "percent": round(suggested_percent, 3),
        "reason": "Stake dinâmica combina probabilidade, confiança, EV, risco, drawdown, sequência, exposição e correlação.",
    }


def multiple_probability(probabilities: list[int], correlation_factors: list[float] | None = None) -> int:
    if not probabilities:
        return 0
    raw = prod(max(0.01, min(0.99, p / 100.0)) for p in probabilities)
    factor = prod(correlation_factors or [1.0] * len(probabilities))
    return max(1, min(99, round(raw * factor * 100)))


def model_metadata() -> dict[str, Any]:
    return {
        "version": MODEL_VERSION,
        "released_at": datetime.now(timezone.utc).date().isoformat(),
        "principles": [
            "Amostra insuficiente reduz confiança.",
            "Probabilidade não é garantia.",
            "IA interpreta; não substitui a probabilidade-base.",
            "Correlação reduz stake e probabilidade combinada.",
        ],
    }
