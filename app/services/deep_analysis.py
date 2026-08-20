from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict
from statistics import mean
from typing import Any

from app.services.sports import SportsApiError, SportsService


@dataclass
class TeamDeepStats:
    team_id: int
    team: str
    sample: int
    contextual_sample: int
    goals_for: float
    goals_against: float
    ht_goals_total: float
    corners_for: float
    corners_against: float
    shots_for: float
    shots_against: float
    shots_on_target_for: float
    under_3_5_hits: int
    over_1_5_hits: int
    under_1_5_ht_hits: int
    under_10_5_corners_hits: int
    over_8_5_corners_hits: int
    opponent_strength_index: float


def _avg(values: list[float]) -> float:
    return round(mean(values), 2) if values else 0.0


def _team_stat(rows: list[dict], team_id: int, stat_type: str) -> float | None:
    for row in rows:
        if int(row.get("team", {}).get("id") or 0) != team_id:
            continue
        for stat in row.get("statistics", []):
            if stat.get("type") != stat_type:
                continue
            value = stat.get("value")
            if value is None:
                return None
            try:
                return float(str(value).replace("%", ""))
            except (TypeError, ValueError):
                return None
    return None


def _opponent_stat(rows: list[dict], team_id: int, stat_type: str) -> float | None:
    for row in rows:
        if int(row.get("team", {}).get("id") or 0) == team_id:
            continue
        for stat in row.get("statistics", []):
            if stat.get("type") != stat_type:
                continue
            value = stat.get("value")
            if value is None:
                return None
            try:
                return float(str(value).replace("%", ""))
            except (TypeError, ValueError):
                return None
    return None


class DeepAnalysisService:
    def __init__(self):
        self.sports = SportsService()

    async def _standings_strength(self, league_id: int, season: int, team_id: int) -> float:
        try:
            payload = await self.sports._get("/standings", {"league": league_id, "season": season})
            groups = payload.get("response", [])
            rows = groups[0].get("league", {}).get("standings", [[]])[0] if groups else []
            if not rows:
                return 50.0
            total = len(rows)
            for row in rows:
                if int(row.get("team", {}).get("id") or 0) == team_id:
                    rank = int(row.get("rank") or total)
                    return round(100.0 * (total - rank) / max(total - 1, 1), 1)
        except Exception:
            pass
        return 50.0

    async def _profile_team(self, team_id: int, team_name: str, wanted_home: bool, league_id: int, season: int) -> TeamDeepStats:
        games = await self.sports.last_five(team_id)
        completed = [g for g in games if g.get("fixture", {}).get("status", {}).get("short") in {"FT", "AET", "PEN"}][:5]
        stats = await asyncio.gather(
            *(self.sports.fixture_statistics(int(g["fixture"]["id"])) for g in completed),
            return_exceptions=True,
        )
        gf: list[float] = []; ga: list[float] = []; ht: list[float] = []
        cf: list[float] = []; ca: list[float] = []; sf: list[float] = []; sa: list[float] = []; sot: list[float] = []
        under35 = over15 = under15ht = under105c = over85c = 0
        contextual = 0
        for game, stat_rows in zip(completed, stats):
            home_id = int(game.get("teams", {}).get("home", {}).get("id") or 0)
            is_home = home_id == team_id
            if is_home == wanted_home:
                contextual += 1
            goals = game.get("goals", {})
            hg, ag = goals.get("home"), goals.get("away")
            if hg is not None and ag is not None:
                team_goals = float(hg if is_home else ag); opp_goals = float(ag if is_home else hg)
                gf.append(team_goals); ga.append(opp_goals)
                total = team_goals + opp_goals
                under35 += int(total < 3.5); over15 += int(total > 1.5)
            half = game.get("score", {}).get("halftime", {})
            hh, ha = half.get("home"), half.get("away")
            if hh is not None and ha is not None:
                htotal = float(hh + ha); ht.append(htotal); under15ht += int(htotal < 1.5)
            if isinstance(stat_rows, Exception):
                continue
            team_c = _team_stat(stat_rows, team_id, "Corner Kicks")
            opp_c = _opponent_stat(stat_rows, team_id, "Corner Kicks")
            team_s = _team_stat(stat_rows, team_id, "Total Shots")
            opp_s = _opponent_stat(stat_rows, team_id, "Total Shots")
            team_sot = _team_stat(stat_rows, team_id, "Shots on Goal")
            if team_c is not None: cf.append(team_c)
            if opp_c is not None: ca.append(opp_c)
            if team_s is not None: sf.append(team_s)
            if opp_s is not None: sa.append(opp_s)
            if team_sot is not None: sot.append(team_sot)
            if team_c is not None and opp_c is not None:
                tc = team_c + opp_c; under105c += int(tc < 10.5); over85c += int(tc > 8.5)
        strength = await self._standings_strength(league_id, season, team_id)
        return TeamDeepStats(team_id, team_name, len(completed), contextual, _avg(gf), _avg(ga), _avg(ht), _avg(cf), _avg(ca), _avg(sf), _avg(sa), _avg(sot), under35, over15, under15ht, under105c, over85c, strength)

    async def fixture_context(self, fixture_id: int) -> dict[str, Any]:
        payload = await self.sports._get("/fixtures", {"id": fixture_id})
        rows = payload.get("response", [])
        if not rows:
            raise SportsApiError("Partida não encontrada")
        row = rows[0]
        league = row.get("league", {})
        league_id = int(league.get("id") or 0); season = int(league.get("season") or 0)
        home = row.get("teams", {}).get("home", {}); away = row.get("teams", {}).get("away", {})
        home_id = int(home.get("id") or 0); away_id = int(away.get("id") or 0)
        home_stats, away_stats, h2h_payload = await asyncio.gather(
            self._profile_team(home_id, str(home.get("name") or ""), True, league_id, season),
            self._profile_team(away_id, str(away.get("name") or ""), False, league_id, season),
            self.sports._get("/fixtures/headtohead", {"h2h": f"{home_id}-{away_id}", "last": 5}),
        )
        h2h = h2h_payload.get("response", [])
        home_wins = draws = away_wins = 0
        for g in h2h:
            hg = g.get("goals", {}).get("home"); ag = g.get("goals", {}).get("away")
            if hg is None or ag is None: continue
            hteam = int(g.get("teams", {}).get("home", {}).get("id") or 0)
            if hg == ag: draws += 1
            elif (hg > ag and hteam == home_id) or (ag > hg and hteam != home_id): home_wins += 1
            else: away_wins += 1
        total_games = home_stats.sample + away_stats.sample
        def combined_hits(attr: str) -> dict[str, Any]:
            h = int(getattr(home_stats, attr)); a = int(getattr(away_stats, attr)); total = max(total_games, 1)
            return {"home": f"{h}/{home_stats.sample}", "away": f"{a}/{away_stats.sample}", "combined": f"{h+a}/{total_games}", "percent": round((h+a)/total*100)}
        return {
            "fixture_id": fixture_id,
            "league": str(league.get("name") or ""),
            "home": asdict(home_stats),
            "away": asdict(away_stats),
            "frequencies": {
                "under_3_5_goals": combined_hits("under_3_5_hits"),
                "over_1_5_goals": combined_hits("over_1_5_hits"),
                "under_1_5_ht": combined_hits("under_1_5_ht_hits"),
                "under_10_5_corners": combined_hits("under_10_5_corners_hits"),
                "over_8_5_corners": combined_hits("over_8_5_corners_hits"),
            },
            "h2h": {"sample": len(h2h), "home_wins": home_wins, "draws": draws, "away_wins": away_wins, "weight": 0.05, "note": "H2H é fator complementar, com peso baixo."},
            "strength": {
                "home": home_stats.opponent_strength_index,
                "away": away_stats.opponent_strength_index,
                "note": "Índice de força usa a posição relativa atual na competição quando disponível.",
            },
            "home_away_note": "Mandante é avaliado com contexto casa; visitante com contexto fora. Amostra contextual pequena reduz confiança.",
        }
