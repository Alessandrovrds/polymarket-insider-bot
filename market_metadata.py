"""
Client minimal pour la Gamma API de Polymarket (métadonnées de marché).
Doc officielle : https://docs.polymarket.com/api-reference/markets/list-markets

Utilisé pour : (1) enrichir les alertes déjà détectées, et (2) calculer des
seuils de détection ADAPTATIFS à la taille de chaque marché (voir config.py).
"""
from datetime import datetime, timezone
import json
import time
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
    METADATA_CACHE_TTL_MINUTES,
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


def _fetch_raw_market(condition_id: str) -> dict | None:
    try:
        resp = requests.get(
            GAMMA_MARKETS_URL,
            params={"condition_ids": condition_id, "limit": 1},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else None
    except Exception:
        return None


def fetch_current_outcome_price(condition_id: str, outcome_index: int | None) -> float | None:
    """
    Prix actuel d'une issue précise d'un marché (pour le suivi court terme du
    feedback loop). outcome_index None -> on ne peut pas identifier l'issue,
    retourne None plutôt que de deviner.
    """
    if outcome_index is None:
        return None

    market = _fetch_raw_market(condition_id)
    if not market:
        return None

    try:
        prices = json.loads(market.get("outcomePrices", "[]"))
        return float(prices[outcome_index])
    except (ValueError, IndexError, TypeError, json.JSONDecodeError):
        return None


def fetch_market_resolution(condition_id: str) -> dict:
    """
    Statut de résolution d'un marché (pour le suivi long terme du feedback loop).
    Retourne {"closed": bool, "winning_outcome_index": int|None}.
    """
    market = _fetch_raw_market(condition_id)
    if not market:
        return {"closed": False, "winning_outcome_index": None}

    closed = bool(market.get("closed"))
    winning_index = None
    if closed:
        try:
            prices = json.loads(market.get("outcomePrices", "[]"))
            for i, p in enumerate(prices):
                if float(p) >= 0.99:  # l'issue gagnante résout à un prix ~1.0
                    winning_index = i
                    break
        except (ValueError, TypeError, json.JSONDecodeError):
            pass

    return {"closed": closed, "winning_outcome_index": winning_index}


def _metadata_to_cache_entry(metadata: dict, fetched_at: float) -> dict:
    end_date = metadata.get("end_date")
    return {
        "volume24hr": metadata.get("volume24hr"),
        "liquidity_num": metadata.get("liquidity_num"),
        "end_date_iso": end_date.isoformat() if end_date else None,
        "fetched_at": fetched_at,
    }


def _cache_entry_to_metadata(entry: dict) -> dict:
    end_date = _parse_iso(entry.get("end_date_iso")) if entry.get("end_date_iso") else None
    proximity_hours = None
    if end_date:
        proximity_hours = max((end_date - datetime.now(timezone.utc)).total_seconds() / 3600, 0)
    return {
        "volume24hr": entry.get("volume24hr"),
        "end_date": end_date,
        "proximity_hours": proximity_hours,
        "liquidity_num": entry.get("liquidity_num"),
    }


def fetch_market_metadata_batch_cached(condition_ids: list[str], state: dict) -> dict[str, dict]:
    """
    Comme fetch_market_metadata_batch, mais réutilise un cache stocké dans
    state.json (state["metadata_cache"]) tant qu'il a moins de
    METADATA_CACHE_TTL_MINUTES. Le volume 24h d'un marché ne change pas assez
    vite pour justifier de le re-télécharger toutes les 5 minutes -> ça
    économise des appels réseau et accélère chaque scan.
    """
    condition_ids = list(dict.fromkeys(c for c in condition_ids if c))
    if not condition_ids:
        return {}

    cache = state.setdefault("metadata_cache", {})
    now = time.time()
    ttl_seconds = METADATA_CACHE_TTL_MINUTES * 60

    result: dict[str, dict] = {}
    to_fetch = []
    for cid in condition_ids:
        entry = cache.get(cid)
        if entry and (now - entry.get("fetched_at", 0)) < ttl_seconds:
            result[cid] = _cache_entry_to_metadata(entry)
        else:
            to_fetch.append(cid)

    if to_fetch:
        fresh = fetch_market_metadata_batch(to_fetch)
        for cid, metadata in fresh.items():
            result[cid] = metadata
            cache[cid] = _metadata_to_cache_entry(metadata, now)

    # purge du cache : on ne garde que les marchés vus récemment (évite un state.json qui grossit indéfiniment)
    stale_cutoff = now - ttl_seconds * 6
    for cid in list(cache.keys()):
        if cache[cid].get("fetched_at", 0) < stale_cutoff:
            del cache[cid]

    return result
