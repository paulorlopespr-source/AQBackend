from app.models.entities import LegStatus
from app.services.settlement import settle_leg, settle_total


def test_over_25_win():
    result = settle_total("OVER", 3, 2.5, 1.80)
    assert result.status == LegStatus.WIN.value
    assert result.multiplier == 1.80


def test_asian_225_half_loss():
    result = settle_total("OVER", 2, 2.25, 2.0)
    assert result.status == LegStatus.HALF_LOSS.value
    assert result.multiplier == 0.5


def test_asian_275_half_win():
    result = settle_total("OVER", 3, 2.75, 2.0)
    assert result.status == LegStatus.HALF_WIN.value
    assert result.multiplier == 1.5


def test_suggested_goals_market_is_settled():
    result = settle_leg("gols_ft_over_2.5", "OVER", 2.5, 1.80, {"home_goals": 2, "away_goals": 1})
    assert result.status == LegStatus.WIN.value


def test_double_chance_1x_is_settled():
    result = settle_leg("dupla_chance_1x", "1X", None, 1.30, {"home_goals": 1, "away_goals": 1})
    assert result.status == LegStatus.WIN.value
