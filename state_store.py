"""
Persistance simple dans un fichier JSON pour éviter d'envoyer deux fois
la même alerte. Ce fichier est commité dans le repo GitHub par le workflow
Actions après chaque scan (voir .github/workflows/scan.yml).
"""
import json
import os
import time
from config import STATE_FILE, STATE_MAX_AGE_HOURS, CORRELATION_WINDOW_HOURS, CONTRADICTION_WINDOW_HOURS


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"alerted": {}, "overrides": {}, "telegram_offset": 0}
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        state = {}
    state.setdefault("alerted", {})
    state.setdefault("overrides", {})
    state.setdefault("telegram_offset", 0)
    state.setdefault("wallet_activity", {})
    state.setdefault("market_signal_history", {})
    return state


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def filter_new_alerts(alerts: list[dict], state: dict) -> list[dict]:
    """Retire les alertes déjà envoyées récemment et met à jour l'état."""
    now = time.time()
    alerted = state.setdefault("alerted", {})

    # purge des vieilles entrées
    max_age = STATE_MAX_AGE_HOURS * 3600
    for key in list(alerted.keys()):
        if now - alerted[key] > max_age:
            del alerted[key]

    new_alerts = []
    for alert in alerts:
        key = alert["key"]
        if key not in alerted:
            alerted[key] = now
            new_alerts.append(alert)

    return new_alerts


def is_paused(state: dict) -> bool:
    paused_until = state.get("overrides", {}).get("paused_until")
    return bool(paused_until) and time.time() < paused_until


def get_min_severity(state: dict, default: int) -> int:
    override = state.get("overrides", {}).get("min_severity")
    return override if override is not None else default


def find_cross_market_wallets(state: dict, wallets: list[str], condition_id: str) -> list[str]:
    """
    Parmi `wallets`, retourne ceux qui sont déjà apparus dans une alerte sur
    un AUTRE marché (condition_id différent) au cours des CORRELATION_WINDOW_HOURS
    dernières heures. Un wallet coordonné sur plusieurs marchés en même temps
    est un signal beaucoup plus fort qu'un cluster isolé.
    """
    now = time.time()
    cutoff = now - CORRELATION_WINDOW_HOURS * 3600
    registry = state.get("wallet_activity", {})

    cross_market = []
    for wallet in wallets:
        entries = registry.get(wallet, [])
        other_markets = {e["conditionId"] for e in entries if e["timestamp"] >= cutoff and e["conditionId"] != condition_id}
        if other_markets:
            cross_market.append(wallet)

    return cross_market


def record_wallet_activity(state: dict, wallets: list[str], condition_id: str) -> None:
    """Enregistre que ces wallets viennent d'apparaître dans une alerte sur ce marché."""
    now = time.time()
    cutoff = now - CORRELATION_WINDOW_HOURS * 3600
    registry = state.setdefault("wallet_activity", {})

    for wallet in wallets:
        entries = [e for e in registry.get(wallet, []) if e["timestamp"] >= cutoff]
        entries.append({"conditionId": condition_id, "timestamp": now})
        registry[wallet] = entries

    # purge des wallets qui n'ont plus aucune entrée récente
    for wallet in list(registry.keys()):
        registry[wallet] = [e for e in registry[wallet] if e["timestamp"] >= cutoff]
        if not registry[wallet]:
            del registry[wallet]


def find_conflicting_market_signal(state: dict, condition_id: str, outcome: str, side: str) -> dict | None:
    """
    Cherche, parmi les alertes déjà ENVOYÉES sur ce même marché dans les
    CONTRADICTION_WINDOW_HOURS dernières heures, une alerte qui pariait dans
    la direction OPPOSÉE :
      - même issue mais sens opposé (ex: BUY 'Yes' puis SELL 'Yes'), ou
      - issue différente avec le même sens (ex: BUY 'Yes' puis BUY 'No')
    Retourne la plus récente trouvée, ou None.
    """
    now = time.time()
    cutoff = now - CONTRADICTION_WINDOW_HOURS * 3600
    entries = state.get("market_signal_history", {}).get(condition_id, [])
    recent = [e for e in entries if e["timestamp"] >= cutoff]

    for entry in sorted(recent, key=lambda e: e["timestamp"], reverse=True):
        same_outcome_opposite_side = entry["outcome"] == outcome and entry["side"] != side
        different_outcome_same_side = entry["outcome"] != outcome and entry["side"] == side
        if same_outcome_opposite_side or different_outcome_same_side:
            return entry

    return None


def record_market_signal(state: dict, condition_id: str, outcome: str, side: str, severity_score: int) -> None:
    """Mémorise la direction d'une alerte ENVOYÉE, pour pouvoir détecter une contradiction future."""
    now = time.time()
    cutoff = now - CONTRADICTION_WINDOW_HOURS * 3600
    registry = state.setdefault("market_signal_history", {})

    entries = [e for e in registry.get(condition_id, []) if e["timestamp"] >= cutoff]
    entries.append({"outcome": outcome, "side": side, "timestamp": now, "severity_score": severity_score})
    registry[condition_id] = entries

    # purge des marchés qui n'ont plus aucune entrée récente
    for cid in list(registry.keys()):
        registry[cid] = [e for e in registry[cid] if e["timestamp"] >= cutoff]
        if not registry[cid]:
            del registry[cid]
