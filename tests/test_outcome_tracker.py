import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import outcome_tracker  # noqa: E402
from outcome_tracker import record_alert_outcome, review_short_term, review_long_term, get_stats, format_stats_message  # noqa: E402


def _make_alert(key="a1", side="BUY", outcome_index=0, price=0.5, fresh=False):
    return {
        "key": key, "type": "WHALE", "conditionId": "0xmarket", "title": "Test Market",
        "outcome": "Yes", "outcomeIndex": outcome_index, "side": side,
        "current_price": price, "severity_score": 7,
        "wallet_reputation": {"fresh_ratio": 1.0 if fresh else 0.0},
        "cross_market_wallets": [], "news": {"found": False},
    }


def test_record_alert_outcome_creates_tracked_entry():
    state = {}
    record_alert_outcome(state, _make_alert())
    assert "a1" in state["tracked_alerts"]
    assert state["tracked_alerts"]["a1"]["price_at_alert"] == 0.5
    assert state["tracked_alerts"]["a1"]["short_term"] is None
    print("OK: test_record_alert_outcome_creates_tracked_entry")


def test_short_term_review_marks_correct_when_price_moved_up_on_buy(monkeypatch):
    state = {}
    record_alert_outcome(state, _make_alert(price=0.5, side="BUY"))
    state["tracked_alerts"]["a1"]["sent_at"] = time.time() - 999999  # bien assez vieux

    monkeypatch.setattr(outcome_tracker, "fetch_current_outcome_price", lambda cid, idx: 0.7)

    n = review_short_term(state)
    assert n == 1
    history = state.get("alert_history") or []
    entry = history[0] if history else state["tracked_alerts"].get("a1")
    assert entry["short_term"]["correct"] is True
    print("OK: test_short_term_review_marks_correct_when_price_moved_up_on_buy")


def test_long_term_review_marks_correct_when_predicted_outcome_wins(monkeypatch):
    state = {}
    record_alert_outcome(state, _make_alert(outcome_index=0, side="BUY"))

    monkeypatch.setattr(
        outcome_tracker, "fetch_market_resolution",
        lambda cid: {"closed": True, "winning_outcome_index": 0},
    )

    n = review_long_term(state)
    assert n == 1
    history = state.get("alert_history") or []
    entry = history[0] if history else state["tracked_alerts"].get("a1")
    assert entry["long_term"]["correct"] is True
    print("OK: test_long_term_review_marks_correct_when_predicted_outcome_wins")


def test_get_stats_computes_win_rate_by_signal():
    state = {"alert_history": [
        {"sent_at": time.time(), "signals": {"fresh_wallets": True}, "short_term": None,
         "long_term": {"correct": True}},
        {"sent_at": time.time(), "signals": {"fresh_wallets": True}, "short_term": None,
         "long_term": {"correct": False}},
        {"sent_at": time.time(), "signals": {"fresh_wallets": False}, "short_term": None,
         "long_term": {"correct": False}},
    ], "tracked_alerts": {}}

    stats = get_stats(state)
    assert stats["total_alerts"] == 3
    assert stats["long_term"]["n"] == 3
    assert stats["long_term"]["wins"] == 1
    assert stats["by_signal"]["fresh_wallets"]["n_with"] == 2
    print("OK: test_get_stats_computes_win_rate_by_signal")


def test_format_stats_message_handles_empty_data():
    stats = get_stats({"alert_history": [], "tracked_alerts": {}})
    msg = format_stats_message(stats)
    assert "0" in msg
    assert "pas encore" in msg
    print("OK: test_format_stats_message_handles_empty_data")


if __name__ == "__main__":
    class _FakeMonkeypatch:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    mp = _FakeMonkeypatch()
    test_record_alert_outcome_creates_tracked_entry()
    test_short_term_review_marks_correct_when_price_moved_up_on_buy(mp)
    test_long_term_review_marks_correct_when_predicted_outcome_wins(mp)
    test_get_stats_computes_win_rate_by_signal()
    test_format_stats_message_handles_empty_data()
    print("\nTous les tests du feedback loop sont passés ✅")
