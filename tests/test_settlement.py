from app.models.entities import LegStatus
from app.services.settlement import settle_total


def test_over_25_win():
    result = settle_total("OVER", 3, 2.5, 1.80)
    assert result.status == LegStatus.WIN.value
    assert result.multiplier == 1.80


def test_asian_225_half_win():
    result = settle_total("OVER", 2, 2.25, 2.0)
    assert result.status == LegStatus.HALF_LOSS.value
    assert result.multiplier == 0.5


def test_asian_275_half_win():
    result = settle_total("OVER", 3, 2.75, 2.0)
    assert result.status == LegStatus.HALF_WIN.value
    assert result.multiplier == 1.5
