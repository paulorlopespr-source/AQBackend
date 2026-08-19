from __future__ import annotations

import math
from dataclasses import dataclass

from app.models.entities import LegStatus


@dataclass
class LegSettlement:
    status: str
    multiplier: float | None
    reason: str


def _simple_total(side: str, value: float, line: float, odd: float) -> LegSettlement:
    side = side.upper()
    diff = value - line

    if abs(diff) < 1e-9:
        return LegSettlement(LegStatus.PUSH.value, 1.0, "Linha devolvida")

    won = diff > 0 if side == "OVER" else diff < 0
    if won:
        return LegSettlement(LegStatus.WIN.value, odd, "Seleção vencedora")
    return LegSettlement(LegStatus.LOSS.value, 0.0, "Seleção perdida")


def _quarter_parts(line: float) -> tuple[float, float]:
    # Ex.: 2.25 => 2.0 + 2.5; 2.75 => 2.5 + 3.0
    lower = math.floor(line * 2) / 2
    upper = math.ceil(line * 2) / 2
    return lower, upper


def settle_total(side: str, value: float, line: float, odd: float) -> LegSettlement:
    hundredths = int(round(abs(line) * 100)) % 50
    is_quarter = hundredths == 25

    if not is_quarter:
        return _simple_total(side, value, line, odd)

    a_line, b_line = _quarter_parts(line)
    a = _simple_total(side, value, a_line, odd)
    b = _simple_total(side, value, b_line, odd)

    # Metade da stake em cada linha.
    multiplier = ((a.multiplier or 0.0) + (b.multiplier or 0.0)) / 2

    if a.status == b.status:
        return LegSettlement(a.status, multiplier, f"Linha asiática {line}")

    statuses = {a.status, b.status}
    if statuses == {LegStatus.WIN.value, LegStatus.PUSH.value}:
        return LegSettlement(LegStatus.HALF_WIN.value, multiplier, f"Meia vitória em {line}")
    if statuses == {LegStatus.LOSS.value, LegStatus.PUSH.value}:
        return LegSettlement(LegStatus.HALF_LOSS.value, multiplier, f"Meia perda em {line}")

    return LegSettlement(LegStatus.WAITING_STATS.value, None, "Liquidação não suportada")


def settle_leg(
    market_id: str,
    side: str,
    line: float | None,
    odd: float,
    match: dict,
) -> LegSettlement:
    home = match.get("home_goals")
    away = match.get("away_goals")
    if home is None or away is None:
        return LegSettlement(LegStatus.WAITING_STATS.value, None, "Placar ainda indisponível")

    total_goals = home + away

    if market_id == "btts":
        yes = side.upper() in {"YES", "SIM", "OVER"}
        occurred = home > 0 and away > 0
        won = occurred if yes else not occurred
        return LegSettlement(
            LegStatus.WIN.value if won else LegStatus.LOSS.value,
            odd if won else 0.0,
            "Ambas marcam",
        )

    if market_id == "ft_result":
        actual = "HOME" if home > away else "AWAY" if away > home else "DRAW"
        won = side.upper() == actual
        return LegSettlement(
            LegStatus.WIN.value if won else LegStatus.LOSS.value,
            odd if won else 0.0,
            f"Resultado final: {actual}",
        )

    if market_id.startswith(("goals_", "asian_goal_")):
        if line is None:
            return LegSettlement(LegStatus.WAITING_STATS.value, None, "Linha de gols ausente")
        return settle_total(side, float(total_goals), line, odd)

    if market_id.startswith(("corners_", "asian_corners_")):
        corners = match.get("corners")
        if corners is None or line is None:
            return LegSettlement(LegStatus.WAITING_STATS.value, None, "Escanteios ainda indisponíveis")
        return settle_total(side, float(corners), line, odd)

    if market_id.startswith(("cards_", "asian_cards_")):
        cards = match.get("cards")
        if cards is None or line is None:
            return LegSettlement(LegStatus.WAITING_STATS.value, None, "Cartões ainda indisponíveis")
        return settle_total(side, float(cards), line, odd)

    return LegSettlement(
        LegStatus.WAITING_STATS.value,
        None,
        f"Mercado ainda não possui regra automática: {market_id}",
    )
