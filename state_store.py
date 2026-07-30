"""
Persistance simple dans un fichier JSON pour éviter d'envoyer deux fois
la même alerte. Ce fichier est commité dans le repo GitHub par le workflow
Actions après chaque scan (voir .github/workflows/scan.yml).
"""
import json
import os
import time
from config import STATE_FILE, STATE_MAX_AGE_HOURS


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
