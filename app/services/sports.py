from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.sports_cache import SportsCache


class SportsApiError(RuntimeError):
    pass


class SportsService:
    def __init__(self):
        self.settings = get_settings()

    def _headers(self) -> dict[str, str]:
        if not self.settings.sports_api_key:
            raise SportsApiError("SPORTS_API_KEY não configurada no backend")
        return {"x-apisports-key": self.settings.sports_api_key}

    def _ttl_for(self, path: str, params: dict[str, Any]) -> int:
        if path == "/fixtures/statistics":
            return self.settings.sports_cache_statistics_seconds
        if path == "/fixtures" and "last" in params:
            return self.settings.sports_cache_team_form_seconds
        return self.settings.sports_cache_fixtures_seconds

    async def _get(self, path: str, params: dict[str, Any], force_refresh: bool = False) -> dict:
        key = SportsCache.make_key(path, params)

        async def fetcher() -> dict:
            try:
                async with httpx.AsyncClient(
                    base_url=self.settings.sports_api_base_url,
                    timeout=25,
                ) as client:
                    response = await client.get(path, params=params, headers=self._headers())
                    response.raise_for_status()
                    payload = response.json()
            except httpx.HTTPError as exc:
                raise SportsApiError(f"Falha ao consultar API esportiva: {exc}") from exc

            errors = payload.get("errors")
            if errors:
                raise SportsApiError(f"API esportiva retornou erro: {errors}")
            return payload

        payload, _cache_status = await SportsCache.get_or_fetch(
            key=key,
            ttl_seconds=self._ttl_for(path, params),
            stale_seconds=self.settings.sports_cache_stale_seconds,
            fetcher=fetcher,
            force_refresh=force_refresh,
        )
        return payload

    async def fixtures_by_date(self, target_date: date, force_refresh: bool = False) -> list[dict]:
        payload = await self._get(
            "/fixtures",
            {"date": target_date.isoformat(), "timezone": "America/Bahia"},
            force_refresh=force_refresh,
        )
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

    async def last_five(self, team_id: int, force_refresh: bool = False) -> list[dict]:
        payload = await self._get(
            "/fixtures",
            {"team": team_id, "last": 5, "timezone": "America/Bahia"},
            force_refresh=force_refresh,
        )
        return payload.get("response", [])

    async def fixture_final(self, fixture_id: int, force_refresh: bool = False) -> dict | None:
        payload = await self._get("/fixtures", {"id": fixture_id}, force_refresh=force_refresh)
        rows = payload.get("response", [])
        if not rows:
            return None
        row = rows[0]
        status = row["fixture"]["status"]["short"]
        if status not in {"FT", "AET", "PEN"}:
            return None
        return row

    async def fixture_statistics(self, fixture_id: int, force_refresh: bool = False) -> list[dict]:
        payload = await self._get(
            "/fixtures/statistics",
            {"fixture": fixture_id},
            force_refresh=force_refresh,
        )
        return payload.get("response", [])

    async def recent_team_profile(self, team_id: int, team_name: str = "", force_refresh: bool = False) -> dict:
        rows = await self.last_five(team_id, force_refresh=force_refresh)
        completed = [
            row for row in rows
            if row.get("fixture", {}).get("status", {}).get("short") in {"FT", "AET", "PEN"}
        ][:5]

        wins = draws = losses = 0
        goals_for = goals_against = 0.0
        last_five: list[str] = []
        fixture_ids: list[int] = []

        for row in completed:
            home = row["teams"]["home"]["id"] == team_id
            gf = row["goals"]["home"] if home else row["goals"]["away"]
            ga = row["goals"]["away"] if home else row["goals"]["home"]
            if gf is None or ga is None:
                continue
            goals_for += float(gf)
            goals_against += float(ga)
            fixture_ids.append(int(row["fixture"]["id"]))
            if gf > ga:
                wins += 1
                last_five.append("V")
            elif gf == ga:
                draws += 1
                last_five.append("E")
            else:
                losses += 1
                last_five.append("D")

        stat_rows = await asyncio.gather(
            *(self.fixture_statistics(fid, force_refresh=force_refresh) for fid in fixture_ids),
            return_exceptions=True,
        )
        corners: list[float] = []
        shots: list[float] = []
        shots_on_target: list[float] = []

        for stats in stat_rows:
            if isinstance(stats, Exception):
                continue
            team_block = next((x for x in stats if x.get("team", {}).get("id") == team_id), None)
            if not team_block:
                continue
            stat_map = {x.get("type"): x.get("value") for x in team_block.get("statistics", [])}
            c = self._number(stat_map.get("Corner Kicks"))
            s = self._number(stat_map.get("Total Shots"))
            sot = self._number(stat_map.get("Shots on Goal"))
            if c is not None:
                corners.append(c)
            if s is not None:
                shots.append(s)
            if sot is not None:
                shots_on_target.append(sot)

        count = wins + draws + losses
        points = wins * 3 + draws
        score = round(points / (count * 3) * 100) if count else 50
        label = "BOA_FASE" if score >= 67 else "ESTAVEL" if score >= 40 else "MA_FASE"

        return {
            "team_id": team_id,
            "team": team_name or str(team_id),
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "avg_goals_for": round(goals_for / count, 2) if count else 0.0,
            "avg_goals_against": round(goals_against / count, 2) if count else 0.0,
            "avg_corners": round(sum(corners) / len(corners), 2) if corners else 0.0,
            "avg_shots": round(sum(shots) / len(shots), 2) if shots else 0.0,
            "avg_shots_on_target": round(sum(shots_on_target) / len(shots_on_target), 2) if shots_on_target else 0.0,
            "form_score": score,
            "form_label": label,
            "last_five": last_five,
        }

    async def analyze_fixture(self, fixture: dict, force_refresh: bool = False) -> dict:
        home, away = await asyncio.gather(
            self.recent_team_profile(fixture["home_team_id"], fixture["home_team"], force_refresh),
            self.recent_team_profile(fixture["away_team_id"], fixture["away_team"], force_refresh),
        )

        expected_home = max((home["avg_goals_for"] + away["avg_goals_against"]) / 2, 0.0)
        expected_away = max((away["avg_goals_for"] + home["avg_goals_against"]) / 2, 0.0)
        expected_corners = home["avg_corners"] + away["avg_corners"]
        expected_shots = home["avg_shots"] + away["avg_shots"]
        expected_sot = home["avg_shots_on_target"] + away["avg_shots_on_target"]

        form_component = (home["form_score"] + away["form_score"]) / 2
        attack_component = min((expected_home + expected_away) / 3.2 * 100, 100)
        pressure_component = min(expected_shots / 28.0 * 100, 100) if expected_shots > 0 else 50
        data_quality = sum([
            1 if home["avg_shots"] > 0 else 0,
            1 if away["avg_shots"] > 0 else 0,
            1 if home["avg_corners"] > 0 else 0,
            1 if away["avg_corners"] > 0 else 0,
        ]) / 4

        aq_score = round(
            0.45 * form_component +
            0.30 * attack_component +
            0.25 * pressure_component
        )
        aq_score = max(1, min(99, aq_score))
        confidence = "ALTA" if data_quality >= 0.75 and aq_score >= 70 else "MEDIA" if data_quality >= 0.5 else "BAIXA"

        total_goals = expected_home + expected_away
        summary = (
            f"Últimos 5: {home['team']} {home['wins']}V/{home['draws']}E/{home['losses']}D e "
            f"{away['team']} {away['wins']}V/{away['draws']}E/{away['losses']}D. "
            f"Projeção AQ: {total_goals:.2f} gols, {expected_corners:.1f} escanteios e {expected_shots:.1f} finalizações somadas."
        )

        return {
            **fixture,
            "home_form": home,
            "away_form": away,
            "aq_score": aq_score,
            "confidence": confidence,
            "expected_goals_home": round(expected_home, 2),
            "expected_goals_away": round(expected_away, 2),
            "expected_corners": round(expected_corners, 2),
            "expected_shots": round(expected_shots, 2),
            "expected_shots_on_target": round(expected_sot, 2),
            "summary": summary,
        }

    async def analyzed_fixtures_by_date(
        self,
        target_date: date,
        limit: int = 12,
        force_refresh: bool = False,
    ) -> list[dict]:
        fixtures = await self.fixtures_by_date(target_date, force_refresh=force_refresh)
        keywords = (
            "brasileir", "serie a", "serie b", "premier league", "la liga", "bundesliga",
            "eredivisie", "ligue 1", "premiership", "eliteserien", "libertadores", "sudamericana",
        )
        monitored = [
            f for f in fixtures
            if any(k in f["league"].lower() for k in keywords)
        ]
        selected = monitored[:max(1, min(limit, 20))]
        analyses = await asyncio.gather(
            *(self.analyze_fixture(f, force_refresh=force_refresh) for f in selected),
            return_exceptions=True,
        )
        return [x for x in analyses if not isinstance(x, Exception)]

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
    def cache_stats() -> dict[str, int]:
        return SportsCache.stats()

    @staticmethod
    def clear_cache() -> int:
        return SportsCache.clear()

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(str(value).replace("%", ""))
        except (TypeError, ValueError):
            return None

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
