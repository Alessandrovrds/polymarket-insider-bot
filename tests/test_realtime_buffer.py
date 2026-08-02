import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from realtime_scan import TradeBuffer  # noqa: E402


def test_buffer_computes_usd_value():
    buf = TradeBuffer()
    buf.add({"proxyWallet": "0xa", "size": 100, "price": 0.5, "timestamp": time.time()})
    snap = buf.snapshot()
    assert len(snap) == 1
    assert snap[0]["usd_value"] == 50.0
    print("OK: test_buffer_computes_usd_value")


def test_buffer_prunes_old_trades():
    buf = TradeBuffer()
    old_ts = time.time() - 10000  # bien avant la fenêtre glissante
    buf.add({"proxyWallet": "0xold", "size": 100, "price": 0.5, "timestamp": old_ts})
    buf.add({"proxyWallet": "0xnew", "size": 100, "price": 0.5, "timestamp": time.time()})
    snap = buf.snapshot()
    assert len(snap) == 1
    assert snap[0]["proxyWallet"] == "0xnew"
    print("OK: test_buffer_prunes_old_trades")


def test_buffer_ignores_malformed_payload():
    buf = TradeBuffer()
    buf.add({"proxyWallet": "0xbad", "size": "not-a-number", "price": 0.5, "timestamp": time.time()})
    assert len(buf.snapshot()) == 0
    print("OK: test_buffer_ignores_malformed_payload")


if __name__ == "__main__":
    test_buffer_computes_usd_value()
    test_buffer_prunes_old_trades()
    test_buffer_ignores_malformed_payload()
    print("\nTous les tests du buffer temps réel sont passés ✅")
