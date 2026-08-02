"""
Envoie automatiquement un résumé de fiabilité du bot chaque vendredi (une
seule fois dans la journée, même si le scan tourne toutes les 5 minutes).
"""
import time
from datetime import datetime, timezone
from config import WEEKLY_REPORT_ENABLED, WEEKLY_REPORT_WEEKDAY
from outcome_tracker import get_stats, format_stats_message
from telegram_notifier import send_telegram_message


def maybe_send_weekly_report(state: dict) -> bool:
    """Envoie le rapport hebdomadaire si on est vendredi et qu'il n'a pas déjà été envoyé aujourd'hui."""
    if not WEEKLY_REPORT_ENABLED:
        return False

    today = datetime.now(timezone.utc)
    if today.weekday() != WEEKLY_REPORT_WEEKDAY:
        return False

    today_str = today.strftime("%Y-%m-%d")
    if state.get("last_weekly_report_date") == today_str:
        return False  # déjà envoyé aujourd'hui

    since_ts = time.time() - 7 * 86400
    stats = get_stats(state, since_ts=since_ts)
    message = format_stats_message(stats, title="RAPPORT HEBDOMADAIRE (7 derniers jours)")

    try:
        send_telegram_message(message)
    except Exception:
        return False  # on retentera au prochain scan de la journée

    state["last_weekly_report_date"] = today_str
    return True
