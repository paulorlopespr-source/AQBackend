from app.services.advanced_match import adjusted_confidence, entry_class, live_alert, ticket_risk_label


def test_entry_class_thresholds():
    assert entry_class(80) == "FORTE"
    assert entry_class(79) == "CONSISTENTE"
    assert entry_class(70) == "CONSISTENTE"
    assert entry_class(69) == "CAUTELA"
    assert entry_class(60) == "CAUTELA"
    assert entry_class(59) == "EVITAR"


def test_incomplete_sample_reduces_confidence():
    full = adjusted_confidence(10, 10)
    partial = adjusted_confidence(5, 3)
    assert full == 100
    assert partial < full


def test_live_over_ht_alert_requires_pressure():
    signal = live_alert(22, 0, 0, 8, 3, 2)
    assert signal["status"] == "ENTRADA_DETECTADA"
    assert signal["market"] == "Over 0.5 Gols HT"
    wait = live_alert(22, 0, 0, 2, 0, 0)
    assert wait["status"] == "AGUARDAR"


def test_under_line_red_risk():
    status, _ = ticket_risk_label("UNDER ESCANTEIOS", 8.5, 55, 0, 9, 2)
    assert status == "RISCO ELEVADO"
