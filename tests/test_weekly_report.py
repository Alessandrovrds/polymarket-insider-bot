import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import weekly_report  # noqa: E402
from weekly_report import maybe_send_weekly_report  # noqa: E402


def test_sends_report_on_friday_if_not_already_sent(monkeypatch):
    sent = {"called": False}
    monkeypatch.setattr(weekly_report, "send_telegram_message", lambda text: sent.update(called=True))

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 31, 10, 0, tzinfo=timezone.utc)  # un vendredi

    monkeypatch.setattr(weekly_report, "datetime", FakeDatetime)

    state = {"alert_history": [], "tracked_alerts": {}}
    result = maybe_send_weekly_report(state)

    assert result is True
    assert sent["called"] is True
    assert state["last_weekly_report_date"] == "2026-07-31"
    print("OK: test_sends_report_on_friday_if_not_already_sent")


def test_does_not_send_twice_same_day(monkeypatch):
    monkeypatch.setattr(weekly_report, "send_telegram_message", lambda text: None)

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 31, 15, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(weekly_report, "datetime", FakeDatetime)

    state = {"alert_history": [], "tracked_alerts": {}, "last_weekly_report_date": "2026-07-31"}
    result = maybe_send_weekly_report(state)
    assert result is False
    print("OK: test_does_not_send_twice_same_day")


def test_does_not_send_on_non_friday(monkeypatch):
    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 29, 10, 0, tzinfo=timezone.utc)  # un mercredi

    monkeypatch.setattr(weekly_report, "datetime", FakeDatetime)

    state = {}
    result = maybe_send_weekly_report(state)
    assert result is False
    print("OK: test_does_not_send_on_non_friday")


if __name__ == "__main__":
    class _FakeMonkeypatch:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    mp = _FakeMonkeypatch()
    test_sends_report_on_friday_if_not_already_sent(mp)
    test_does_not_send_twice_same_day(mp)
    test_does_not_send_on_non_friday(mp)
    print("\nTous les tests du rapport hebdomadaire sont passés ✅")
