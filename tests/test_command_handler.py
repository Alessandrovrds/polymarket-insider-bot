import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from command_handler import _handle_command  # noqa: E402


def test_pause_sets_paused_until_in_future():
    state = {"overrides": {}}
    reply = _handle_command("/pause 30", state)
    assert "30 minutes" in reply
    assert state["overrides"]["paused_until"] > time.time()
    print("OK: test_pause_sets_paused_until_in_future")


def test_resume_clears_pause():
    state = {"overrides": {"paused_until": time.time() + 1000}}
    reply = _handle_command("/resume", state)
    assert "réactivées" in reply
    assert "paused_until" not in state["overrides"]
    print("OK: test_resume_clears_pause")


def test_severite_updates_override_and_clamps_range():
    state = {"overrides": {}}
    _handle_command("/severite 15", state)  # au-dessus de 10 -> clampé
    assert state["overrides"]["min_severity"] == 10
    print("OK: test_severite_updates_override_and_clamps_range")


def test_unknown_command_returns_none():
    state = {"overrides": {}}
    reply = _handle_command("/bla", state)
    assert reply is None
    print("OK: test_unknown_command_returns_none")


def test_status_reports_current_overrides():
    state = {"overrides": {"min_severity": 7}}
    reply = _handle_command("/status", state)
    assert "7/10" in reply
    print("OK: test_status_reports_current_overrides")


if __name__ == "__main__":
    test_pause_sets_paused_until_in_future()
    test_resume_clears_pause()
    test_severite_updates_override_and_clamps_range()
    test_unknown_command_returns_none()
    test_status_reports_current_overrides()
    print("\nTous les tests de commandes sont passés ✅")
