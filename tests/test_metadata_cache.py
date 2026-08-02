import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import market_metadata  # noqa: E402


def test_cache_avoids_second_network_call(monkeypatch):
    call_count = {"n": 0}

    def fake_fetch_batch(condition_ids):
        call_count["n"] += 1
        return {cid: {"volume24hr": 1000, "end_date": None, "proximity_hours": None, "liquidity_num": None} for cid in condition_ids}

    monkeypatch.setattr(market_metadata, "fetch_market_metadata_batch", fake_fetch_batch)

    state = {}
    market_metadata.fetch_market_metadata_batch_cached(["0xabc"], state)
    market_metadata.fetch_market_metadata_batch_cached(["0xabc"], state)  # devrait venir du cache

    assert call_count["n"] == 1
    print("OK: test_cache_avoids_second_network_call")


def test_cache_refetches_new_condition_id(monkeypatch):
    call_count = {"n": 0}

    def fake_fetch_batch(condition_ids):
        call_count["n"] += 1
        return {cid: {"volume24hr": 1000, "end_date": None, "proximity_hours": None, "liquidity_num": None} for cid in condition_ids}

    monkeypatch.setattr(market_metadata, "fetch_market_metadata_batch", fake_fetch_batch)

    state = {}
    market_metadata.fetch_market_metadata_batch_cached(["0xabc"], state)
    market_metadata.fetch_market_metadata_batch_cached(["0xdef"], state)  # nouveau -> re-fetch

    assert call_count["n"] == 2
    print("OK: test_cache_refetches_new_condition_id")


if __name__ == "__main__":
    class _FakeMonkeypatch:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    mp = _FakeMonkeypatch()
    test_cache_avoids_second_network_call(mp)
    test_cache_refetches_new_condition_id(mp)
    print("\nTous les tests de cache sont passés ✅")
