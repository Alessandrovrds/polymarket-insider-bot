import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from market_metadata import compute_adaptive_thresholds  # noqa: E402


def test_small_market_uses_floor_not_percentage():
    # 0.05% * $10,000 de volume = $5 -> bien en dessous du plancher $500
    metadata = {"volume24hr": 10000, "proximity_hours": None, "end_date": None, "liquidity_num": None}
    thresholds = compute_adaptive_thresholds(metadata)
    assert thresholds["cluster_min_usd"] == 500  # plancher
    assert thresholds["adaptive"] is True
    print("OK: test_small_market_uses_floor_not_percentage")


def test_huge_market_uses_percentage_not_floor():
    # 5% * $10,000,000 = $500,000 -> bien au-dessus du plancher
    metadata = {"volume24hr": 10_000_000, "proximity_hours": None, "end_date": None, "liquidity_num": None}
    thresholds = compute_adaptive_thresholds(metadata)
    assert thresholds["cluster_min_usd"] == 500_000
    print("OK: test_huge_market_uses_percentage_not_floor")


def test_missing_volume_falls_back_to_static_config():
    metadata = {"volume24hr": None, "proximity_hours": None, "end_date": None, "liquidity_num": None}
    thresholds = compute_adaptive_thresholds(metadata)
    assert thresholds["adaptive"] is False
    assert thresholds["cluster_min_usd"] == 5000  # CLUSTER_MIN_TOTAL_USD par défaut
    print("OK: test_missing_volume_falls_back_to_static_config")


if __name__ == "__main__":
    test_small_market_uses_floor_not_percentage()
    test_huge_market_uses_percentage_not_floor()
    test_missing_volume_falls_back_to_static_config()
    print("\nTous les tests de seuils adaptatifs sont passés ✅")
