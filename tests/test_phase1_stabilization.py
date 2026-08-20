import asyncio

import pytest
from fastapi import HTTPException

from app.api.routes import advanced
from app.services.sports import SportsApiError


class _SportsOk:
    async def analyzed_fixtures_by_date(self, *_args, **_kwargs):
        return [{
            "fixture_id": 10,
            "league": "Liga Teste",
            "kickoff": "2026-08-20T19:00:00-03:00",
            "home_team": "Casa",
            "away_team": "Fora",
            "market_probabilities": [{
                "market": "Total de gols",
                "selection": "Under 3.5",
                "probability": 82,
                "data_confidence": 78,
                "risk": "BAIXO",
                "rationale": "Sinal de teste",
                "fair_odd": 1.22,
                "best_odd": None,
                "bookmaker": None,
                "ev_percent": None,
                "value_label": "SEM ODD",
            }],
        }]


class _SportsUnavailable:
    async def analyzed_fixtures_by_date(self, *_args, **_kwargs):
        raise SportsApiError("indisponível")


class _LiveOk:
    async def live_matches(self, *_args, **_kwargs):
        return []


class _LiveUnavailable:
    async def live_matches(self, *_args, **_kwargs):
        raise SportsApiError("indisponível")


def test_opportunities_keeps_pre_live_when_live_provider_fails(monkeypatch):
    monkeypatch.setattr(advanced, "SportsService", _SportsOk)
    monkeypatch.setattr(advanced, "AdvancedMatchService", _LiveUnavailable)

    result = asyncio.run(advanced.opportunities(min_probability=0))

    assert len(result) == 1
    assert result[0]["mode"] == "PRE_LIVE"


def test_opportunities_returns_structured_503_when_all_sources_fail(monkeypatch):
    monkeypatch.setattr(advanced, "SportsService", _SportsUnavailable)
    monkeypatch.setattr(advanced, "AdvancedMatchService", _LiveUnavailable)

    with pytest.raises(HTTPException) as error:
        asyncio.run(advanced.opportunities())

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "SPORTS_PROVIDER_UNAVAILABLE"


def test_missing_sports_key_has_actionable_non_retryable_code(monkeypatch):
    from app.services.sports import SportsService

    service = SportsService()
    monkeypatch.setattr(service.settings, "sports_api_key", "")

    with pytest.raises(SportsApiError) as error:
        service._headers()

    assert error.value.code == "SPORTS_API_NOT_CONFIGURED"
    assert error.value.retryable is False
