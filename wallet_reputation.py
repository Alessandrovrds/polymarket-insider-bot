"""
Réputation des wallets via data-api.polymarket.com/traded — indique sur
combien de marchés DIFFÉRENTS un wallet a déjà tradé (toute son histoire).

Deux usages opposés de ce même chiffre :
- Wallet "frais" (peu de marchés tradés) qui apparaît soudain dans un
  cluster synchronisé -> signal d'insider plus fort.
- Wallet "market maker" (ÉNORMÉMENT de marchés tradés, souvent des bots de
  liquidité qui tradent partout en permanence) -> signal beaucoup plus
  faible, voire du bruit à filtrer : ce n'est pas un insider, c'est juste
  un robot qui fait son travail habituel.

Les appels réseau sont parallélisés (ThreadPoolExecutor) pour ne pas
ralentir le scan quand une alerte implique plusieurs wallets.
"""
from concurrent.futures import ThreadPoolExecutor
import requests
from config import (
    FRESH_WALLET_MAX_MARKETS,
    MAX_WALLETS_CHECKED_PER_ALERT,
    MARKET_MAKER_MIN_MARKETS,
    WALLET_CHECK_MAX_WORKERS,
)

TRADED_URL = "https://data-api.polymarket.com/traded"


def fetch_traded_count(wallet: str) -> int | None:
    """Nombre de marchés différents tradés par ce wallet. None si erreur/inconnu."""
    try:
        resp = requests.get(TRADED_URL, params={"user": wallet}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("traded")
    except Exception:
        return None


def assess_wallet_freshness(wallets: list[str]) -> dict:
    """
    Vérifie jusqu'à MAX_WALLETS_CHECKED_PER_ALERT wallets d'une alerte (en
    parallèle) et retourne :
      - checked : nombre de wallets effectivement vérifiés
      - fresh_count / fresh_ratio / fresh_wallets : wallets quasi jamais tradé
      - market_maker_count / market_maker_ratio : wallets très probablement
        des bots de liquidité (traded >= MARKET_MAKER_MIN_MARKETS)
    """
    sample = wallets[:MAX_WALLETS_CHECKED_PER_ALERT]

    with ThreadPoolExecutor(max_workers=WALLET_CHECK_MAX_WORKERS) as pool:
        traded_counts = list(pool.map(fetch_traded_count, sample))

    checked = 0
    fresh_wallets = []
    market_maker_wallets = []

    for wallet, traded in zip(sample, traded_counts):
        if traded is None:
            continue
        checked += 1
        if traded <= FRESH_WALLET_MAX_MARKETS:
            fresh_wallets.append(wallet)
        elif traded >= MARKET_MAKER_MIN_MARKETS:
            market_maker_wallets.append(wallet)

    fresh_ratio = (len(fresh_wallets) / checked) if checked > 0 else None
    market_maker_ratio = (len(market_maker_wallets) / checked) if checked > 0 else None

    return {
        "checked": checked,
        "fresh_count": len(fresh_wallets),
        "fresh_ratio": fresh_ratio,
        "fresh_wallets": fresh_wallets,
        "market_maker_count": len(market_maker_wallets),
        "market_maker_ratio": market_maker_ratio,
        "market_maker_wallets": market_maker_wallets,
    }
