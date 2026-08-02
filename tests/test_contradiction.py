import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from state_store import find_conflicting_market_signal, record_market_signal  # noqa: E402
from scoring import enrich_and_score  # noqa: E402


def test_same_outcome_opposite_side_is_a_conflict():
    state = {}
    record_market_signal(state, "0xmarket", "Yes", "BUY", severity_score=6)
    conflict = find_conflicting_market_signal(state, "0xmarket", "Yes", "SELL")
    assert conflict is not None
    assert conflict["side"] == "BUY"
    print("OK: test_same_outcome_opposite_side_is_a_conflict")


def test_different_outcome_same_side_is_a_conflict():
    state = {}
    record_market_signal(state, "0xmarket", "Yes", "BUY", severity_score=6)
    conflict = find_conflicting_market_signal(state, "0xmarket", "No", "BUY")
    assert conflict is not None
    print("OK: test_different_outcome_same_side_is_a_conflict")


def test_same_direction_is_not_a_conflict():
    state = {}
    record_market_signal(state, "0xmarket", "Yes", "BUY", severity_score=6)
    conflict = find_conflicting_market_signal(state, "0xmarket", "Yes", "BUY")
    assert conflict is None
    print("OK: test_same_direction_is_not_a_conflict")


def test_different_market_is_not_a_conflict():
    state = {}
    record_market_signal(state, "0xmarket1", "Yes", "BUY", severity_score=6)
    conflict = find_conflicting_market_signal(state, "0xmarket2", "No", "BUY")
    assert conflict is None
    print("OK: test_different_market_is_not_a_conflict")


def test_conflict_reduces_score_and_warns_in_recommendation():
    alert = {
        "type": "WHALE", "key": "test", "conditionId": "0xmarket", "title": "Test",
        "eventSlug": "test", "slug": "test", "outcome": "Yes", "side": "BUY",
        "wallets": ["0xw1"], "total_usd": 30000, "timestamp": time.time(), "current_price": 0.5,
    }
    metadata = {"volume24hr": None, "proximity_hours": None, "end_date": None, "liquidity_num": None}

    without_conflict = enrich_and_score(dict(alert), metadata)

    conflict = {"outcome": "Yes", "side": "SELL", "timestamp": time.time() - 600, "severity_score": 7}
    with_conflict = enrich_and_score(dict(alert), metadata, conflicting_signal=conflict)

    assert with_conflict["severity_score"] < without_conflict["severity_score"]
    assert "CONTRADICTOIRE" in with_conflict["severity_label"]
    assert "ATTENTION" in with_conflict["recommendation"]
    # l'avertissement doit être en tête du message, pas noyé dans les raisons
    assert with_conflict["recommendation"].startswith("⚡ ATTENTION")
    print("OK: test_conflict_reduces_score_and_warns_in_recommendation")


if __name__ == "__main__":
    test_same_outcome_opposite_side_is_a_conflict()
    test_different_outcome_same_side_is_a_conflict()
    test_same_direction_is_not_a_conflict()
    test_different_market_is_not_a_conflict()
    test_conflict_reduces_score_and_warns_in_recommendation()
    print("\nTous les tests de contradiction sont passés ✅")
