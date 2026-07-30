"""
Envoi des alertes sur Telegram via l'API Bot HTTP standard.
Nécessite TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID en variables d'environnement.
"""
import os
import requests
from config import DIGEST_THRESHOLD_COUNT, DIGEST_TOP_N


def _short(addr: str) -> str:
    return f"{addr[:6]}...{addr[-4:]}" if addr else "?"


def _market_url(alert: dict) -> str:
    if alert.get("eventSlug"):
        return f"https://polymarket.com/event/{alert['eventSlug']}"
    if alert.get("slug"):
        return f"https://polymarket.com/market/{alert['slug']}"
    return "https://polymarket.com"


def format_alert(alert: dict) -> str:
    title = alert.get("title") or "(marché inconnu)"
    outcome = alert.get("outcome") or "?"
    side = alert.get("side") or "?"
    total = alert.get("total_usd", 0)
    url = _market_url(alert)
    severity = alert.get("severity_label", "")
    recommendation = alert.get("recommendation", "")

    if alert["type"] == "CLUSTER":
        wallets = alert["wallets"]
        wallets_str = "\n".join(f"  • {_short(w)}" for w in wallets[:10])
        extra = f"\n  ... +{len(wallets) - 10} autres" if len(wallets) > 10 else ""
        return (
            f"🚨 CLUSTER SUSPECT DÉTECTÉ — sévérité {severity}\n\n"
            f"📊 {title}\n"
            f"➡️ {side} sur « {outcome} »\n"
            f"👥 {len(wallets)} wallets en {alert.get('span_seconds', 0):.0f}s\n"
            f"💰 Total : ${total:,.0f}\n\n"
            f"💡 SUGGESTION DE TRADE\n{recommendation}\n\n"
            f"Wallets :\n{wallets_str}{extra}\n\n"
            f"🔗 {url}"
        )
    else:  # WHALE
        wallet = alert["wallets"][0]
        return (
            f"🐋 GROSSE TRANSACTION ISOLÉE — sévérité {severity}\n\n"
            f"📊 {title}\n"
            f"➡️ {side} sur « {outcome} »\n"
            f"💰 Montant : ${total:,.0f}\n"
            f"👤 Wallet : {_short(wallet)}\n\n"
            f"💡 SUGGESTION DE TRADE\n{recommendation}\n\n"
            f"🔗 {url}"
        )


def format_digest(alerts: list[dict]) -> str:
    """Regroupe plusieurs alertes en un seul message compact (anti-spam)."""
    ranked = sorted(alerts, key=lambda a: a.get("severity_score", 0), reverse=True)
    shown, rest = ranked[:DIGEST_TOP_N], ranked[DIGEST_TOP_N:]

    lines = [f"📬 DIGEST : {len(alerts)} alertes détectées ce scan\n"]
    for a in shown:
        icon = "🚨" if a["type"] == "CLUSTER" else "🐋"
        outcome = a.get("outcome") or "?"
        side = a.get("side") or "?"
        title = a.get("title") or "(marché inconnu)"
        lines.append(
            f"{icon} {a.get('severity_label', '')} — {title}\n"
            f"   {side} « {outcome} » · ${a.get('total_usd', 0):,.0f} · {_market_url(a)}"
        )

    if rest:
        lines.append(f"\n... +{len(rest)} autre(s) alerte(s) de sévérité plus faible (non détaillées).")

    return "\n\n".join(lines)


def send_telegram_message(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID doivent être définis "
            "(en secrets GitHub Actions, voir README.md)."
        )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Pas de parse_mode : les titres de marché viennent de Polymarket et
    # peuvent contenir des caractères (_ * [ ]...) qui cassent le parsing
    # Markdown de Telegram (400 Bad Request). Texte brut = toujours fiable.
    resp = requests.post(url, json={
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }, timeout=15)
    resp.raise_for_status()


def notify_alerts(alerts: list[dict]) -> None:
    """
    Envoie les alertes sur Telegram. Si trop d'alertes arrivent dans le même
    scan (> DIGEST_THRESHOLD_COUNT), elles sont groupées en un seul message
    digest pour éviter de spammer le chat.
    """
    if not alerts:
        return
    if len(alerts) > DIGEST_THRESHOLD_COUNT:
        send_telegram_message(format_digest(alerts))
    else:
        for alert in alerts:
            send_telegram_message(format_alert(alert))
