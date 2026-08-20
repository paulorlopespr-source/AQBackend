from __future__ import annotations

import asyncio
import math
from typing import Any

from app.services.sports import SportsApiError, SportsService

MONITORED_LEAGUE_KEYWORDS = (
    "brasileir", "serie a", "serie b", "premier league", "la liga", "bundesliga",
    "eredivisie", "ligue 1", "premiership", "eliteserien", "libertadores", "sudamericana",
)


def entry_class(probability: int) -> str:
    if probability >= 80:
        return "FORTE"
    if probability >= 70:
        return "CONSISTENTE"
    if probability >= 60:
        return "CAUTELA"
    return "EVITAR"


def adjusted_confidence(sample_games: int, stat_games: int) -> int:
    """Conservative confidence: incomplete samples reduce, never increase, confidence."""
    sample = min(max(sample_games, 0) / 10.0, 1.0)
    stats = min(max(stat_games, 0) / 10.0, 1.0)
    return round((0.60 * sample + 0.40 * stats) * 100)


def poisson_over(lam: float, line: float) -> float:
    lam = max(lam, 0.01)
    threshold = math.floor(line)
    cdf = sum(math.exp(-lam) * (lam ** k) / math.factorial(k) for k in range(threshold + 1))
    return max(0.0, min(1.0, 1.0 - cdf))


def build_signal(market: str, selection: str, probability: float, confidence: int, reason: str, period: str) -> dict:
    p = max(1, min(99, round(probability * 100)))
    risk = "BAIXO" if p >= 80 and confidence >= 80 else "MODERADO" if p >= 68 and confidence >= 60 else "ALTO"
    if confidence < 60:
        risk = "ALTO"
    return {
        "period": period,
        "market": market,
        "selection": selection,
        "probability": p,
        "confidence": confidence,
        "risk": risk,
        "classification": entry_class(p),
        "reason": reason,
    }


def live_alert(minute: int, home_goals: int, away_goals: int, shots: int, shots_on_target: int, corners: int) -> dict:
    total_goals = home_goals + away_goals
    pressure = min(100, shots * 4 + shots_on_target * 8 + corners * 3)
    if 15 <= minute <= 30 and total_goals == 0 and shots >= 6 and shots_on_target >= 2:
        probability = min(88, 55 + shots * 2 + shots_on_target * 4)
        return {
            "status": "ENTRADA_DETECTADA",
            "market": "Over 0.5 Gols HT",
            "probability": probability,
            "risk": "BAIXO" if probability >= 80 else "MODERADO",
            "message": "0x0 dentro da janela operacional com volume ofensivo e finalizações no alvo suficientes.",
            "pressure_index": pressure,
        }
    if minute >= 60 and total_goals <= 1 and shots <= 18 and shots_on_target <= 6:
        probability = min(86, 65 + max(0, minute - 60) // 2)
        return {
            "status": "ENTRADA_DETECTADA",
            "market": "Under gols ao vivo",
            "probability": probability,
            "risk": "MODERADO",
            "message": "Partida avançada com placar baixo e volume ofensivo controlado.",
            "pressure_index": pressure,
        }
    return {
        "status": "AGUARDAR",
        "market": "",
        "probability": 0,
        "risk": "MODERADO",
        "message": "As condições operacionais ainda não foram confirmadas.",
        "pressure_index": pressure,
    }


def ticket_risk_label(selection: str, line: float | None, minute: int, goals: int, corners: int, shots_on_target: int) -> tuple[str, str]:
    text = selection.upper()
    if "UNDER" in text and line is not None:
        current = corners if "CANT" in text or "ESCANT" in text else goals
        margin = line - current
        if margin <= 0:
            return "RISCO ELEVADO", "A linha Under já foi alcançada ou ultrapassada."
        if margin <= 1 and minute < 80:
            return "ATENÇÃO", "A margem restante da linha Under está pequena para o tempo restante."
    if "OVER" in text and line is not None:
        current = corners if "CANT" in text or "ESCANT" in text else goals
        missing = line - current
        if minute >= 70 and missing >= 2 and shots_on_target <= 5:
            return "RISCO ELEVADO", "O mercado Over precisa de eventos demais para o tempo e pressão atuais."
        if minute >= 55 and missing >= 1:
            return "ATENÇÃO", "O mercado Over está abaixo do ritmo necessário."
    return "NORMAL", "A condição atual ainda está compatível com a entrada."


class AdvancedMatchService:
    def __init__(self):
        self.sports = SportsService()

    async def decision_card(self, fixture_id: int, force_refresh: bool = False) -> dict:
        payload = await self.sports._get("/fixtures", {"id": fixture_id}, force_refresh=force_refresh)
        rows = payload.get("response", [])
        if not rows:
            raise SportsApiError("Partida não encontrada")
        row = rows[0]
        home = row["teams"]["home"]
        away = row["teams"]["away"]

        home_rows, away_rows = await asyncio.gather(
            self.sports.last_five(home["id"], force_refresh=force_refresh),
            self.sports.last_five(away["id"], force_refresh=force_refresh),
        )
        ht_totals: list[float] = []
        ft_totals: list[float] = []
        fixture_ids: list[int] = []
        contextual_games = 0

        for team_id, recent, wanted_home in ((home["id"], home_rows, True), (away["id"], away_rows, False)):
            for game in recent[:5]:
                if game.get("fixture", {}).get("status", {}).get("short") not in {"FT", "AET", "PEN"}:
                    continue
                is_home = game.get("teams", {}).get("home", {}).get("id") == team_id
                if is_home == wanted_home:
                    contextual_games += 1
                ht = game.get("score", {}).get("halftime", {})
                hg, ag = ht.get("home"), ht.get("away")
                if hg is not None and ag is not None:
                    ht_totals.append(float(hg + ag))
                goals = game.get("goals", {})
                fg, fa = goals.get("home"), goals.get("away")
                if fg is not None and fa is not None:
                    ft_totals.append(float(fg + fa))
                fid = game.get("fixture", {}).get("id")
                if fid:
                    fixture_ids.append(int(fid))

        stats_results = await asyncio.gather(
            *(self.sports.fixture_statistics(fid, force_refresh=force_refresh) for fid in fixture_ids[:10]),
            return_exceptions=True,
        )
        ft_corners: list[float] = []
        ft_shots: list[float] = []
        for stats in stats_results:
            if isinstance(stats, Exception):
                continue
            corners = self.sports._sum_stat(stats, "Corner Kicks")
            shots = self.sports._sum_stat(stats, "Total Shots")
            if corners is not None:
                ft_corners.append(float(corners))
            if shots is not None:
                ft_shots.append(float(shots))

        sample_games = min(len(ft_totals), 10)
        stat_games = max(len(ft_corners), len(ft_shots))
        confidence = adjusted_confidence(sample_games, stat_games)
        ht_lambda = sum(ht_totals) / len(ht_totals) if ht_totals else (sum(ft_totals) / len(ft_totals) * 0.46 if ft_totals else 1.0)
        projected_ht_corners = (sum(ft_corners) / len(ft_corners) * 0.48) if ft_corners else 0.0
        projected_ht_shots = (sum(ft_shots) / len(ft_shots) * 0.47) if ft_shots else 0.0

        signals = []
        for line in (0.5, 1.5):
            over = poisson_over(ht_lambda, line)
            signals.append(build_signal("Gols HT", f"Over {line}", over, confidence, f"Média recente de {ht_lambda:.2f} gols no 1º tempo.", "HT"))
            signals.append(build_signal("Gols HT", f"Under {line}", 1 - over, confidence, f"Média recente de {ht_lambda:.2f} gols no 1º tempo.", "HT"))
        if projected_ht_corners > 0:
            for line in (4.5, 5.5):
                over = poisson_over(projected_ht_corners, line)
                signals.append(build_signal("Escanteios HT", f"Over {line}", over, confidence, f"Projeção HT de {projected_ht_corners:.1f} cantos baseada no ritmo FT recente.", "HT"))
                signals.append(build_signal("Escanteios HT", f"Under {line}", 1 - over, confidence, f"Projeção HT de {projected_ht_corners:.1f} cantos baseada no ritmo FT recente.", "HT"))
        signals.sort(key=lambda item: item["probability"], reverse=True)

        top = next((s for s in signals if s["classification"] in {"FORTE", "CONSISTENTE"} and s["confidence"] >= 60), signals[0] if signals else None)
        prelive = "Sem entrada pré-live forte; aguardar confirmação ao vivo."
        live = "Reavaliar entre 15–30 min usando placar, finalizações no alvo, escanteios e ritmo."
        if top:
            prelive = f"{top['market']} • {top['selection']} — {top['probability']}% ({top['classification'].lower()})."
            if top["market"] == "Gols HT" and top["selection"].startswith("Under"):
                live = "Se permanecer 0x0 entre 15–30 min, confirmar baixa pressão antes de entrar no Under HT."
            elif top["market"] == "Gols HT":
                live = "Entre 15–30 min, confirmar pelo menos 6 finalizações e 2 no alvo antes de considerar Over 0.5 HT."

        return {
            "fixture_id": fixture_id,
            "home_team": home["name"],
            "away_team": away["name"],
            "data_confidence": confidence,
            "contextual_sample_games": contextual_games,
            "ht_goals_avg": round(ht_lambda, 2),
            "ht_corners_projection": round(projected_ht_corners, 2),
            "ht_shots_projection": round(projected_ht_shots, 2),
            "ht_stats_note": "Gols HT usam placares reais de intervalo; cantos e finalizações HT são projeções proporcionais do histórico FT quando a fonte não fornece recorte HT histórico.",
            "signals": signals[:8],
            "prelive_strategy": prelive,
            "live_strategy": live,
        }

    async def live_matches(self, force_refresh: bool = True, limit: int = 12) -> list[dict]:
        payload = await self.sports._get("/fixtures", {"live": "all", "timezone": "America/Bahia"}, force_refresh=force_refresh)
        rows = [r for r in payload.get("response", []) if any(k in r.get("league", {}).get("name", "").lower() for k in MONITORED_LEAGUE_KEYWORDS)][:limit]
        results: list[dict] = []
        for row in rows:
            fixture = row["fixture"]
            fid = int(fixture["id"])
            try:
                stats = await self.sports.fixture_statistics(fid, force_refresh=True)
            except Exception:
                stats = []
            shots = self.sports._sum_stat(stats, "Total Shots") or 0
            sot = self.sports._sum_stat(stats, "Shots on Goal") or 0
            corners = self.sports._sum_stat(stats, "Corner Kicks") or 0
            yellow = self.sports._sum_stat(stats, "Yellow Cards") or 0
            red = self.sports._sum_stat(stats, "Red Cards") or 0
            minute = int(fixture.get("status", {}).get("elapsed") or 0)
            home_goals = int(row.get("goals", {}).get("home") or 0)
            away_goals = int(row.get("goals", {}).get("away") or 0)
            alert = live_alert(minute, home_goals, away_goals, shots, sot, corners)
            results.append({
                "fixture_id": fid,
                "league": row.get("league", {}).get("name", ""),
                "home_team": row.get("teams", {}).get("home", {}).get("name", ""),
                "away_team": row.get("teams", {}).get("away", {}).get("name", ""),
                "minute": minute,
                "status": fixture.get("status", {}).get("short", ""),
                "home_goals": home_goals,
                "away_goals": away_goals,
                "shots": shots,
                "shots_on_target": sot,
                "corners": corners,
                "cards": yellow + red,
                "alert": alert,
            })
        return results
