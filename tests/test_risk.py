from app.services.risk import analyze_ticket


def test_high_risk():
    result = analyze_ticket([60, 60])
    assert result["probability"] < 50
    assert result["risk_label"] == "ALTO"


def test_good_single_entry():
    result = analyze_ticket([85])
    assert result["probability"] == 85
    assert result["risk_label"] == "BAIXO"
