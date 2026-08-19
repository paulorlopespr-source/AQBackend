from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from app.core.config import get_settings


class SportsApiError(RuntimeError):
    pass


class SportsService:
    def __init__(self):
        self.settings = get_settings()

    def _headers(self) -> dict[str, str]:
        if not self.settings.sports_api_key:
            raise SportsApiError("SPORTS_API_KEY não configurada no backend")
        return {"x-apisports-key": self.settings.sports_api_key}

    async def _get(self, path: str, params: dict[str, Any]) -> dict:
        async with httpx.AsyncClient(
            base_url=self.settings.sports_api_base_url,
            timeout=25,
        ) as client:
            response = await client.get(path, params=params, headers=self._headers())
            response.raise_for_status()
            payload = response.json()

        errors = payload.get("errors")
        if errors:
            raise SportsApiError(f"API esportiva retornou erro: {errors}")
        return payload

    async def fixtures_by_date(self, target_date: date) -> list[dict]:
        payload = await self._get("/fixtures", {"date": target_date.isoformat()})
        out = []
        for row in payload.get("response", []):
            fixture = row["fixture"]
            league = row["league"]
            teams = row["teams"]
            goals = row["goals"]
            out.append({
                "fixture_id": fixture["id"],
                "league": league["name"],
                "kickoff": fixture["date"],
                "home_team_id": teams["home"]["id"],
                "home_team": teams["home"]["name"],
                "away_team_id": teams["away"]["id"],
                "away_team": teams["away"]["name"],
                "status": fixture["status"]["short"],
                "home_goals": goals["home"],
                "away_goals": goals["away"],
            })
        return out

    async def last_five(self, team_id: int) -> list[dict]:
        payload = await self._get("/fixtures", {"team": team_id, "last": 5})
        return payload.get("response", [])

    async def fixture_final(self, fixture_id: int) -> dict | None:
        payload = await self._get("/fixtures", {"id": fixture_id})
        rows = payload.get("response", [])
        if not rows:
            return None
        row = rows[0]
        status = row["fixture"]["status"]["short"]
        if status not in {"FT", "AET", "PEN"}:
            return None
        return row

    async def fixture_statistics(self, fixture_id: int) -> list[dict]:
        payload = await self._get("/fixtures/statistics", {"fixture": fixture_id})
        return payload.get("response", [])

    async def final_match_data(self, fixture_id: int) -> dict | None:
        final = await self.fixture_final(fixture_id)
        if final is None:
            return None

        stats = await self.fixture_statistics(fixture_id)
        corners = self._sum_stat(stats, "Corner Kicks")
        yellow = self._sum_stat(stats, "Yellow Cards")
        red = self._sum_stat(stats, "Red Cards")

        cards = None
        if yellow is not None or red is not None:
            cards = (yellow or 0) + (red or 0)

        return {
            "fixture_id": fixture_id,
            "home_goals": final["goals"]["home"],
            "away_goals": final["goals"]["away"],
            "corners": corners,
            "cards": cards,
            "status": final["fixture"]["status"]["short"],
        }

    @staticmethod
    def _sum_stat(rows: list[dict], stat_type: str) -> int | None:
        found = False
        total = 0
        for row in rows:
            for stat in row.get("statistics", []):
                if stat.get("type") != stat_type:
                    continue
                value = stat.get("value")
                if value is None:
                    continue
                try:
                    numeric = int(float(str(value).replace("%", "")))
                except ValueError:
                    continue
                found = True
                total += numeric
        return total if found else None
