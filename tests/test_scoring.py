import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from detector import detect_wallet_clusters, detect_whale_trades  # noqa: E402
from scoring import enrich_and_score  # noqa: E402
from test_detector import make_trade  # noqa: E402


def test_cluster_with_strong_signals_gets_high_severity():
    now = time.time()
    trades = [
        make_trade(f"0xwallet{i}", 20000, 0.5, now - (10 - i)) for i in range(8)
    ]
    # prix qui bouge fort sur le dernier trade -> price_move_pct élevé
    trades[-1]["price"] = 0.65
    trades[-1]["usd_value"] = 20000 * 0.65

    alerts = detect_wallet_clusters(trades)
    assert len(alerts) == 1

    metadata = {"volume24hr": 50000, "end_date": None, "proximity_hours": 10, "liquidity_num": 10000}
    scored = enrich_and_score(alerts[0], metadata)

    assert scored["severity_score"] >= 8
    assert "ACHETER" in scored["recommendation"]
    print("OK: test_cluster_with_strong_signals_gets_high_severity")


def test_whale_with_no_metadata_still_scores() -> None:
    now = time.time()
    trades = [make_trade("0xbigwallet", 100000, 0.5, now - 1)]  # 50 000$
    alerts = detect_whale_trades(trades)
    assert len(alerts) == 1

    metadata = {"volume24hr": None, "end_date": None, "proximity_hours": None, "liquidity_num": None}
    scored = enrich_and_score(alerts[0], metadata)

    assert scored["severity_score"] >= 5  # base 2 + gros montant 4 = 6
    assert scored["relative_volume"] is None
    assert "recommendation" in scored
    print("OK: test_whale_with_no_metadata_still_scores")


def test_recommendation_says_sell_when_side_is_sell():
    now = time.time()
    trades = [make_trade("0xbigwallet", 100000, 0.5, now - 1, side="SELL")]
    alerts = detect_whale_trades(trades)
    metadata = {"volume24hr": None, "end_date": None, "proximity_hours": None, "liquidity_num": None}
    scored = enrich_and_score(alerts[0], metadata)
    assert "VENDRE" in scored["recommendation"]
    print("OK: test_recommendation_says_sell_when_side_is_sell")


def test_fresh_wallets_boost_severity_score():
    now = time.time()
    trades = [make_trade("0xbigwallet", 40000, 0.5, now - 1)]  # 20 000$ -> score de base modeste
    alerts = detect_whale_trades(trades)
    metadata = {"volume24hr": None, "end_date": None, "proximity_hours": None, "liquidity_num": None}

    without_reputation = enrich_and_score(alerts[0], metadata, reputation=None)
    with_fresh_wallets = enrich_and_score(
        alerts[0], metadata, reputation={"checked": 1, "fresh_count": 1, "fresh_ratio": 1.0, "fresh_wallets": ["0xbigwallet"]}
    )

    assert with_fresh_wallets["severity_score"] > without_reputation["severity_score"]
    assert "frais" in with_fresh_wallets["recommendation"]
    print("OK: test_fresh_wallets_boost_severity_score")


def test_adaptive_threshold_gates_detection_on_small_market():
    # cluster de 8000$ : détecté avec le seuil fixe (5000$), mais PAS avec un
    # seuil adaptatif élevé calculé sur un marché à gros volume
    from market_metadata import compute_adaptive_thresholds

    now = time.time()
    trades = [
        make_trade("0xw1", 5000, 0.5, now - 5, condition_id="0xbig"),
        make_trade("0xw2", 3000, 0.5, now - 3, condition_id="0xbig"),
        make_trade("0xw3", 8000, 0.5, now - 1, condition_id="0xbig"),
    ]  # total = 8000$

    # sans seuil adaptatif -> détecté (8000 >= 5000 par défaut)
    assert len(detect_wallet_clusters(trades)) == 1

    # avec un marché énorme -> seuil adaptatif = 5% * 50M = 2.5M$, donc PAS détecté
    huge_market_meta = {"volume24hr": 50_000_000, "proximity_hours": None, "end_date": None, "liquidity_num": None}
    thresholds = {"0xbig": compute_adaptive_thresholds(huge_market_meta)}
    assert len(detect_wallet_clusters(trades, thresholds)) == 0
    print("OK: test_adaptive_threshold_gates_detection_on_small_market")


if __name__ == "__main__":
    test_cluster_with_strong_signals_gets_high_severity()
    test_whale_with_no_metadata_still_scores()
    test_recommendation_says_sell_when_side_is_sell()
    test_fresh_wallets_boost_severity_score()
    test_adaptive_threshold_gates_detection_on_small_market()
    print("\nTous les tests de scoring sont passés ✅")
