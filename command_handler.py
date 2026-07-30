"""
Bot Telegram interactif. Comme le scan tourne toutes les 5 minutes (GitHub
Actions), les commandes ne sont PAS traitées instantanément : elles sont
lues et appliquées au prochain passage du scan (délai de quelques minutes).
Une vraie interactivité temps réel nécessiterait un hébergement en continu
(amélioration future n°1 : WebSocket + petit serveur toujours actif).

Commandes supportées :
  /status           -> état actuel du bot (seuils, pause, dernière exécution)
  /pause <minutes>  -> suspend les alertes pendant N minutes
  /resume           -> annule la pause
  /severite <0-10>  -> change le seuil minimum de sévérité pour cette session
  /aide             -> liste des commandes
"""
import os
import time
import requests
from config import (
    TELEGRAM_GETUPDATES_URL_TMPL,
    TELEGRAM_SENDMESSAGE_URL_TMPL,
    MIN_SEVERITY_SCORE,
)

HELP_TEXT = (
    "🤖 *Commandes disponibles*\n\n"
    "/status — état actuel du bot\n"
    "/pause <minutes> — suspend les alertes\n"
    "/resume — annule la pause\n"
    "/severite <0-10> — change le seuil de sévérité minimum\n"
    "/aide — cette liste\n\n"
    "⏱️ Les commandes sont appliquées au prochain scan (jusqu'à ~5 min de délai)."
)


def _get_updates(offset: int) -> list[dict]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return []
    url = TELEGRAM_GETUPDATES_URL_TMPL.format(token=token)
    try:
        resp = requests.get(url, params={"offset": offset, "timeout": 0}, timeout=15)
        resp.raise_for_status()
        return resp.json().get("result", [])
    except Exception:
        return []


def _reply(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    url = TELEGRAM_SENDMESSAGE_URL_TMPL.format(token=token)
    try:
        requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }, timeout=15)
    except Exception:
        pass  # une notif ratée ne doit pas faire planter le scan


def _handle_command(text: str, state: dict) -> str:
    parts = text.strip().split()
    cmd = parts[0].lower()
    overrides = state.setdefault("overrides", {})

    if cmd in ("/status", "/statut"):
        paused_until = overrides.get("paused_until")
        pause_str = "aucune" if not paused_until or time.time() >= paused_until else (
            f"jusqu'à dans {(paused_until - time.time()) / 60:.0f} min"
        )
        severity = overrides.get("min_severity", MIN_SEVERITY_SCORE)
        return (
            f"📊 *Statut du bot*\n\n"
            f"Seuil de sévérité minimum : {severity}/10\n"
            f"Pause : {pause_str}\n"
            f"Dernier scan : à l'instant"
        )

    if cmd == "/pause":
        minutes = 60
        if len(parts) > 1:
            try:
                minutes = max(1, int(parts[1]))
            except ValueError:
                pass
        overrides["paused_until"] = time.time() + minutes * 60
        return f"⏸️ Alertes suspendues pendant {minutes} minutes."

    if cmd == "/resume":
        overrides.pop("paused_until", None)
        return "▶️ Alertes réactivées."

    if cmd in ("/severite", "/severity"):
        if len(parts) > 1:
            try:
                value = max(0, min(10, int(parts[1])))
                overrides["min_severity"] = value
                return f"✅ Seuil de sévérité réglé à {value}/10."
            except ValueError:
                pass
        return "Usage : /severite <0-10>"

    if cmd in ("/aide", "/help", "/start"):
        return HELP_TEXT

    return None  # commande inconnue -> pas de réponse (évite le bruit)


def process_pending_commands(state: dict) -> int:
    """
    Récupère les messages Telegram reçus depuis le dernier scan, applique les
    commandes reconnues, répond à l'utilisateur, et met à jour l'offset dans
    l'état persistant. Retourne le nombre de commandes traitées.
    """
    offset = state.get("telegram_offset", 0)
    updates = _get_updates(offset)
    processed = 0

    for update in updates:
        state["telegram_offset"] = update["update_id"] + 1
        message = update.get("message", {})
        text = message.get("text", "")
        if not text.startswith("/"):
            continue

        reply = _handle_command(text, state)
        if reply:
            _reply(reply)
            processed += 1

    return processed
