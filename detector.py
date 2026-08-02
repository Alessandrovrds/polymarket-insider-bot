"""
Détection des anomalies dans un lot de trades Polymarket.

Deux types de signaux :

1. CLUSTER  : plusieurs wallets DIFFÉRENTS prennent la même position
              (même marché, même issue, même sens) en l'espace de
              quelques secondes, pour un montant cumulé important.
              -> pattern typique d'un "leak" d'information qui circule.

2. WHALE    : un seul wallet place un trade isolé anormalement gros.
              -> pattern typique d'un insider qui agit seul.
"""
import time
from collections import defaultdict
from config import (
    LOOKBACK_MINUTES,
    CLUSTER_WINDOW_SECONDS,
    CLUSTER_MIN_WALLETS,
    CLUSTER_MIN_TOTAL_USD,
    SINGLE_TRADE_MIN_USD,
)


def _recent_only(trades: list[dict]) -> list[dict]:
    cutoff = time.time() - LOOKBACK_MINUTES * 60
    return [t for t in trades if t.get("timestamp", 0) >= cutoff]


def detect_whale_trades(trades: list[dict], market_thresholds: dict | None = None) -> list[dict]:
    """
    Trades isolés anormalement gros. Si market_thresholds est fourni
    (voir market_metadata.build_market_thresholds), le seuil $ est adapté
    à la taille de chaque marché ; sinon on retombe sur SINGLE_TRADE_MIN_USD.
    """
    market_thresholds = market_thresholds or {}
    alerts = []
    for t in _recent_only(trades):
        threshold = market_thresholds.get(t.get("conditionId"), {}).get("whale_min_usd", SINGLE_TRADE_MIN_USD)
        if t["usd_value"] >= threshold:
            alerts.append({
                "type": "WHALE",
                "key": f"whale:{t.get('transactionHash')}",
                "conditionId": t.get("conditionId"),
                "title": t.get("title"),
                "eventSlug": t.get("eventSlug"),
                "slug": t.get("slug"),
                "outcome": t.get("outcome"),
                "outcomeIndex": t.get("outcomeIndex"),
                "side": t.get("side"),
                "wallets": [t.get("proxyWallet")],
                "total_usd": t["usd_value"],
                "timestamp": t.get("timestamp"),
                "current_price": t.get("price"),
                "threshold_used": threshold,
            })
    return alerts


def detect_wallet_clusters(trades: list[dict], market_thresholds: dict | None = None) -> list[dict]:
    """
    Regroupe les trades par (marché, issue, sens), puis cherche des
    fenêtres glissantes de CLUSTER_WINDOW_SECONDS contenant au moins
    CLUSTER_MIN_WALLETS wallets distincts pour un total >= seuil du marché
    (adaptatif si market_thresholds est fourni, sinon CLUSTER_MIN_TOTAL_USD).
    """
    market_thresholds = market_thresholds or {}
    groups = defaultdict(list)
    for t in _recent_only(trades):
        key = (t.get("conditionId"), t.get("outcome"), t.get("side"))
        groups[key].append(t)

    alerts = []
    for (condition_id, outcome, side), group_trades in groups.items():
        group_trades.sort(key=lambda t: t.get("timestamp", 0))

        n = len(group_trades)
        start = 0
        window_by_key = {}  # cluster_key -> alerte la plus complète vue jusqu'ici
        for end in range(n):
            window_end_time = group_trades[end]["timestamp"]
            # avance la borne gauche de la fenêtre pour rester dans CLUSTER_WINDOW_SECONDS
            while group_trades[start]["timestamp"] < window_end_time - CLUSTER_WINDOW_SECONDS:
                start += 1

            window = group_trades[start:end + 1]
            distinct_wallets = {w["proxyWallet"] for w in window}
            total_usd = sum(w["usd_value"] for w in window)
            cluster_threshold = market_thresholds.get(condition_id, {}).get("cluster_min_usd", CLUSTER_MIN_TOTAL_USD)

            if len(distinct_wallets) >= CLUSTER_MIN_WALLETS and total_usd >= cluster_threshold:
                first_ts = window[0]["timestamp"]
                last_ts = window[-1]["timestamp"]
                sample = window[0]

                price_start = window[0]["price"]
                price_end = window[-1]["price"]
                price_move_pct = (
                    (price_end - price_start) / price_start * 100 if price_start else 0.0
                )

                # clé arrondie à la fenêtre pour éviter les doublons d'une exécution à l'autre
                cluster_key = f"cluster:{condition_id}:{outcome}:{side}:{first_ts // CLUSTER_WINDOW_SECONDS}"

                # on garde la fenêtre la plus complète (le plus de wallets/volume) pour cette clé
                candidate = {
                    "type": "CLUSTER",
                    "key": cluster_key,
                    "conditionId": condition_id,
                    "title": sample.get("title"),
                    "eventSlug": sample.get("eventSlug"),
                    "slug": sample.get("slug"),
                    "outcome": outcome,
                    "outcomeIndex": sample.get("outcomeIndex"),
                    "side": side,
                    "wallets": sorted(distinct_wallets),
                    "total_usd": total_usd,
                    "timestamp": last_ts,
                    "span_seconds": last_ts - first_ts,
                    "price_start": price_start,
                    "price_end": price_end,
                    "price_move_pct": price_move_pct,
                    "current_price": price_end,
                    "threshold_used": cluster_threshold,
                }
                existing = window_by_key.get(cluster_key)
                if existing is None or len(candidate["wallets"]) >= len(existing["wallets"]):
                    window_by_key[cluster_key] = candidate

        alerts.extend(window_by_key.values())

    return alerts


def detect_anomalies(trades: list[dict], market_thresholds: dict | None = None) -> list[dict]:
    """Point d'entrée : combine les deux détecteurs."""
    return detect_wallet_clusters(trades, market_thresholds) + detect_whale_trades(trades, market_thresholds)
