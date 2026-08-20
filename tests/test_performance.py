from app.services.performance import bucket_for_probability
from app.services.advanced_match import adjusted_confidence, entry_class, live_alert


def test_probability_classification_boundaries():
    assert entry_class(80) == "FORTE"
    assert entry_class(70) == "CONSISTENTE"
    assert entry_class(60) == "CAUTELA"
    assert entry_class(59) == "EVITAR"


def test_probability_buckets():
    assert bucket_for_probability(88) == "80-99"
    assert bucket_for_probability(74) == "70-79"
    assert bucket_for_probability(65) == "60-69"
    assert bucket_for_probability(42) == "01-59"


def test_incomplete_sample_reduces_confidence():
    assert adjusted_confidence(10, 10) == 100
    assert adjusted_confidence(4, 2) < adjusted_confidence(10, 10)


def test_live_alert_requires_conditions():
    assert live_alert(20, 0, 0, 7, 3, 2)["status"] == "ENTRADA_DETECTADA"
    assert live_alert(8, 0, 0, 7, 3, 2)["status"] == "AGUARDAR"
