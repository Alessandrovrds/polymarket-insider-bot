"""
Client minimal pour la Data API publique de Polymarket.
Doc officielle : https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets
"""
import requests
from config import POLYMARKET_TRADES_URL, POLL_LIMIT


def fetch_recent_trades(limit: int = POLL_LIMIT) -> list[dict]:
    """
    Récupère les trades les plus récents sur TOUT Polymarket (pas de filtre
    market/user -> vue globale de la plateforme).

    Chaque trade contient notamment :
      proxyWallet, side, size, price, timestamp, conditionId,
      title, slug, eventSlug, outcome, transactionHash
    """
    params = {
        "limit": limit,
        "offset": 0,
        "takerOnly": "true",  # ne garde que le côté "taker" (celui qui initie le trade)
    }
    resp = requests.get(POLYMARKET_TRADES_URL, params=params, timeout=20)
    resp.raise_for_status()
    trades = resp.json()

    # normalisation minimale + calcul de la valeur en $ du trade
    for t in trades:
        t["usd_value"] = float(t.get("size", 0)) * float(t.get("price", 0))

    return trades
