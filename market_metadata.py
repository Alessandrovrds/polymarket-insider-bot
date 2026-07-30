"""
Client minimal pour la Gamma API de Polymarket (métadonnées de marché).
Doc officielle : https://docs.polymarket.com/api-reference/markets/list-markets

Utilisé pour : (1) enrichir les alertes déjà détectées, et (2) calculer des
seuils de détection ADAPTATIFS à la taille de chaque marché (voir config.py).
"""
from datetime import datetime, timezone
import requests
from config import (
    GAMMA_MARKETS_URL,
    ADAPTIVE_THRESHOLDS_ENABLED,
    ADAPTIVE_CLUSTER_PCT_OF_VOLUME24H,
    ADAPTIVE_WHALE_PCT_OF_VOLUME24H,
    CLUSTER_MIN_TOTAL_USD_FLOOR,
    SINGLE_TRADE_MIN_USD_FLOOR,
    CLUSTER_MIN_TOTAL_USD,
    SINGLE_TRADE_MIN_USD,
)

EMPTY_METADATA = {"volume24hr": None, "end_date": None, "proximity_hours": None, "liquidity_num": None}


def _parse_iso(dt_str: str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_metadata(market: dict) -> dict:
    end_date = _parse_iso(market.get("endDate"))
    proximity_hours = None
    if end_date:
        now = datetime.now(timezone.utc)
        proximity_hours = max((end_date - now).total_seconds() / 3600, 0)

    return {
        "volume24hr": market.get("volume24hr"),
        "end_date": end_date,
        "proximity_hours": proximity_hours,
        "liquidity_num": market.get("liquidityNum"),
    }


def fetch_market_metadata(condition_id: str) -> dict:
    """Métadonnées pour un seul marché (utilisé par les tests / usages ponctuels)."""
    batch = fetch_market_metadata_batch([condition_id])
    return batch.get(condition_id, dict(EMPTY_METADATA))


def fetch_market_metadata_batch(condition_ids: list[str]) -> dict[str, dict]:
    """
    Récupère les métadonnées de plusieurs marchés en UN SEUL appel Gamma API
    (paramètre condition_ids en liste séparée par des virgules, même convention
    que l'endpoint /trades). Retourne un dict conditionId -> metadata.

    En cas d'erreur réseau, retourne un dict vide pour chaque id demandé plutôt
    que de faire planter le scan (l'enrichissement est un bonus, pas une
    dépendance dure).
    """
    condition_ids = list(dict.fromkeys(c for c in condition_ids if c))  # dédup, garde l'ordre
    if not condition_ids:
        return {}

    result = {cid: dict(EMPTY_METADATA) for cid in condition_ids}
    try:
        resp = requests.get(
            GAMMA_MARKETS_URL,
            params={"condition_ids": ",".join(condition_ids), "limit": len(condition_ids)},
            timeout=15,
        )
        resp.raise_for_status()
        markets = resp.json()
    except Exception:
        return result

    for market in markets:
        cid = market.get("conditionId")
        if cid in result:
            result[cid] = _to_metadata(market)

    return result


def compute_adaptive_thresholds(metadata: dict) -> dict:
    """
    Calcule les seuils $ effectifs pour UN marché donné, à partir de son
    volume 24h : effective = max(plancher_absolu, pourcentage * volume24h).

    Si le volume 24h est indisponible (marché tout juste créé, erreur réseau...),
    on retombe sur les constantes fixes CLUSTER_MIN_TOTAL_USD / SINGLE_TRADE_MIN_USD.
    """
    volume24hr = metadata.get("volume24hr")

    if not ADAPTIVE_THRESHOLDS_ENABLED or not volume24hr or volume24hr <= 0:
        return {
            "cluster_min_usd": CLUSTER_MIN_TOTAL_USD,
            "whale_min_usd": SINGLE_TRADE_MIN_USD,
            "adaptive": False,
        }

    return {
        "cluster_min_usd": max(CLUSTER_MIN_TOTAL_USD_FLOOR, ADAPTIVE_CLUSTER_PCT_OF_VOLUME24H * volume24hr),
        "whale_min_usd": max(SINGLE_TRADE_MIN_USD_FLOOR, ADAPTIVE_WHALE_PCT_OF_VOLUME24H * volume24hr),
        "adaptive": True,
    }


def build_market_thresholds(metadata_by_market: dict[str, dict]) -> dict[str, dict]:
    """Applique compute_adaptive_thresholds à un lot entier de marchés."""
    return {cid: compute_adaptive_thresholds(meta) for cid, meta in metadata_by_market.items()}
