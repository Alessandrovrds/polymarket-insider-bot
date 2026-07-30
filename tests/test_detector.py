import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from detector import detect_wallet_clusters, detect_whale_trades  # noqa: E402


def make_trade(wallet, size, price, ts, condition_id="0xabc", outcome="Yes", side="BUY"):
    return {
        "proxyWallet": wallet,
        "side": side,
        "size": size,
        "price": price,
        "usd_value": size * price,
        "timestamp": ts,
        "conditionId": condition_id,
        "title": "Test Market",
        "eventSlug": "test-market",
        "slug": "test-market",
        "outcome": outcome,
        "transactionHash": f"0xhash-{wallet}-{ts}",
    }


def test_cluster_detected_when_many_wallets_close_in_time():
    now = time.time()
    trades = [
        make_trade("0xwallet1", 10000, 0.5, now - 5),
        make_trade("0xwallet2", 8000, 0.5, now - 3),
        make_trade("0xwallet3", 12000, 0.5, now - 1),
    ]
    alerts = detect_wallet_clusters(trades)
    assert len(alerts) == 1
    assert alerts[0]["type"] == "CLUSTER"
    assert len(alerts[0]["wallets"]) == 3
    print("OK: test_cluster_detected_when_many_wallets_close_in_time")


def test_no_cluster_when_wallets_spread_out_in_time():
    now = time.time()
    trades = [
        make_trade("0xwallet1", 10000, 0.5, now - 500),
        make_trade("0xwallet2", 8000, 0.5, now - 300),
        make_trade("0xwallet3", 12000, 0.5, now - 1),
    ]
    alerts = detect_wallet_clusters(trades)
    assert len(alerts) == 0
    print("OK: test_no_cluster_when_wallets_spread_out_in_time")


def test_no_cluster_when_same_wallet_repeats():
    now = time.time()
    trades = [
        make_trade("0xwallet1", 10000, 0.5, now - 5),
        make_trade("0xwallet1", 8000, 0.5, now - 3),
        make_trade("0xwallet1", 12000, 0.5, now - 1),
    ]
    alerts = detect_wallet_clusters(trades)
    assert len(alerts) == 0
    print("OK: test_no_cluster_when_same_wallet_repeats")


def test_whale_trade_detected():
    now = time.time()
    trades = [make_trade("0xbigwallet", 50000, 0.5, now - 1)]  # 25 000$
    alerts = detect_whale_trades(trades)
    assert len(alerts) == 1
    assert alerts[0]["type"] == "WHALE"
    print("OK: test_whale_trade_detected")


def test_small_trade_ignored():
    now = time.time()
    trades = [make_trade("0xsmall", 10, 0.5, now - 1)]  # 5$
    alerts = detect_whale_trades(trades)
    assert len(alerts) == 0
    print("OK: test_small_trade_ignored")


if __name__ == "__main__":
    test_cluster_detected_when_many_wallets_close_in_time()
    test_no_cluster_when_wallets_spread_out_in_time()
    test_no_cluster_when_same_wallet_repeats()
    test_whale_trade_detected()
    test_small_trade_ignored()
    print("\nTous les tests sont passés ✅")
