import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from detector import detect_whale_trades  # noqa: E402
from scoring import enrich_and_score  # noqa: E402
from state_store import find_cross_market_wallets, record_wallet_activity  # noqa: E402
from test_detector import make_trade  # noqa: E402


def test_market_maker_veto_neutralizes_alert():
    now = time.time()
    trades = [make_trade("0xmm", 100000, 0.5, now - 1)]  # 50 000$, très gros
    alerts = detect_whale_trades(trades)
    metadata = {"volume24hr": None, "proximity_hours": None, "end_date": None, "liquidity_num": None}

    # sans réputation -> score normal (élevé, gros montant)
    without_mm = enrich_and_score(alerts[0], metadata)
    assert without_mm["severity_score"] > 0

    # avec 100% de market makers vérifiés -> alerte neutralisée
    mm_reputation = {
        "checked": 1, "fresh_count": 0, "fresh_ratio": 0.0, "fresh_wallets": [],
        "market_maker_count": 1, "market_maker_ratio": 1.0, "market_maker_wallets": ["0xmm"],
    }
    with_mm = enrich_and_score(alerts[0], metadata, reputation=mm_reputation)
    assert with_mm["severity_score"] == 0
    assert "ÉCARTÉE" in with_mm["severity_label"]
    print("OK: test_market_maker_veto_neutralizes_alert")


def test_cross_market_correlation_boosts_score():
    now = time.time()
    trades = [make_trade("0xw1", 3000, 0.5, now - 1)]
    alerts = detect_whale_trades(trades)
    # ce whale seul ne passe même pas le seuil par défaut (5000$ requis) donc on
    # construit une alerte "cluster-like" à la main pour le test de scoring pur
    alert = {
        "type": "WHALE", "key": "test", "conditionId": "0xmarket", "title": "Test",
        "eventSlug": "test", "slug": "test", "outcome": "Yes", "side": "BUY",
        "wallets": ["0xw1"], "total_usd": 15000, "timestamp": now, "current_price": 0.5,
    }
    metadata = {"volume24hr": None, "proximity_hours": None, "end_date": None, "liquidity_num": None}

    without_correlation = enrich_and_score(dict(alert), metadata, cross_market_wallets=[])
    with_correlation = enrich_and_score(dict(alert), metadata, cross_market_wallets=["0xw1", "0xw2"])

    assert with_correlation["severity_score"] > without_correlation["severity_score"]
    assert "coordination" in with_correlation["recommendation"]
    print("OK: test_cross_market_correlation_boosts_score")


def test_news_found_reduces_score():
    alert = {
        "type": "WHALE", "key": "test2", "conditionId": "0xmarket2", "title": "Test",
        "eventSlug": "test", "slug": "test", "outcome": "Yes", "side": "BUY",
        "wallets": ["0xw1"], "total_usd": 30000, "timestamp": time.time(), "current_price": 0.5,
    }
    metadata = {"volume24hr": None, "proximity_hours": None, "end_date": None, "liquidity_num": None}

    without_news = enrich_and_score(dict(alert), metadata, news={"found": False, "headline": None, "checked": True})
    with_news = enrich_and_score(dict(alert), metadata, news={"found": True, "headline": "Big news happened", "checked": True})

    assert with_news["severity_score"] < without_news["severity_score"]
    assert "actualité" in with_news["recommendation"]
    print("OK: test_news_found_reduces_score")


def test_state_store_cross_market_registry():
    state = {"wallet_activity": {}}
    record_wallet_activity(state, ["0xa", "0xb"], "0xmarket1")
    record_wallet_activity(state, ["0xc"], "0xmarket2")

    # 0xa a été vu sur marché1, on cherche s'il apparaît ailleurs pour marché2
    found = find_cross_market_wallets(state, ["0xa", "0xc"], "0xmarket2")
    assert found == ["0xa"]  # 0xa vient d'un AUTRE marché, 0xc est déjà sur ce marché-ci

    # aucun wallet en commun ailleurs
    found_none = find_cross_market_wallets(state, ["0xz"], "0xmarket3")
    assert found_none == []
    print("OK: test_state_store_cross_market_registry")


if __name__ == "__main__":
    test_market_maker_veto_neutralizes_alert()
    test_cross_market_correlation_boosts_score()
    test_news_found_reduces_score()
    test_state_store_cross_market_registry()
    print("\nTous les tests des nouvelles fonctionnalités sont passés ✅")
