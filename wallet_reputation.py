"""
Réputation des wallets via data-api.polymarket.com/traded — indique sur
combien de marchés DIFFÉRENTS un wallet a déjà tradé (toute son histoire).

Un wallet qui n'a quasiment jamais tradé et qui apparaît soudainement dans
un cluster synchronisé est un signal d'insider plus fort qu'un trader actif
habituel qui suit simplement le marché.
"""
import requests
from config import (
    FRESH_WALLET_MAX_MARKETS,
    MAX_WALLETS_CHECKED_PER_ALERT,
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
    Vérifie jusqu'à MAX_WALLETS_CHECKED_PER_ALERT wallets d'une alerte et
    retourne :
      - checked : nombre de wallets effectivement vérifiés
      - fresh_count : combien sont "frais" (traded <= FRESH_WALLET_MAX_MARKETS)
      - fresh_ratio : fresh_count / checked (None si aucun wallet vérifiable)
      - fresh_wallets : liste des wallets frais (pour affichage)
    """
    sample = wallets[:MAX_WALLETS_CHECKED_PER_ALERT]
    checked = 0
    fresh_wallets = []

    for wallet in sample:
        traded = fetch_traded_count(wallet)
        if traded is None:
            continue
        checked += 1
        if traded <= FRESH_WALLET_MAX_MARKETS:
            fresh_wallets.append(wallet)

    fresh_ratio = (len(fresh_wallets) / checked) if checked > 0 else None

    return {
        "checked": checked,
        "fresh_count": len(fresh_wallets),
        "fresh_ratio": fresh_ratio,
        "fresh_wallets": fresh_wallets,
    }
