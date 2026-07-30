"""
Combine les signaux (cluster/whale + métadonnées de marché) en :
  1. Un score de sévérité 0-10 (pour filtrer le bruit)
  2. Une recommandation de trade en français, prête à afficher sur Telegram
"""
from config import (
    CLUSTER_MIN_WALLETS,
    CLUSTER_MIN_TOTAL_USD,
    SINGLE_TRADE_MIN_USD,
    RELATIVE_VOLUME_ALERT_RATIO,
    PROXIMITY_HOURS_ALERT,
    PRICE_MOVE_ALERT_PCT,
    FRESH_WALLET_RATIO_ALERT,
)


def enrich_and_score(alert: dict, metadata: dict, reputation: dict | None = None) -> dict:
    """
    Ajoute severity_score, severity_label, relative_volume, recommendation à
    l'alerte. `reputation` (optionnel) vient de wallet_reputation.assess_wallet_freshness.
    """
    alert = dict(alert)  # copie défensive
    alert.update(metadata)
    if reputation:
        alert["wallet_reputation"] = reputation

    volume24hr = metadata.get("volume24hr") or 0
    relative_volume = (alert["total_usd"] / volume24hr) if volume24hr > 0 else None
    alert["relative_volume"] = relative_volume

    score = 2  # base : l'alerte a déjà passé les seuils de détection

    if alert["type"] == "CLUSTER":
        if len(alert["wallets"]) >= CLUSTER_MIN_WALLETS * 2:
            score += 2
        if alert["total_usd"] >= CLUSTER_MIN_TOTAL_USD * 3:
            score += 2
        if abs(alert.get("price_move_pct", 0)) >= PRICE_MOVE_ALERT_PCT:
            score += 2
    else:  # WHALE
        if alert["total_usd"] >= SINGLE_TRADE_MIN_USD * 2:
            score += 4

    if relative_volume is not None and relative_volume >= RELATIVE_VOLUME_ALERT_RATIO:
        score += 2

    proximity_hours = metadata.get("proximity_hours")
    if proximity_hours is not None and proximity_hours <= PROXIMITY_HOURS_ALERT:
        score += 2

    fresh_ratio = (reputation or {}).get("fresh_ratio")
    if fresh_ratio is not None and fresh_ratio >= FRESH_WALLET_RATIO_ALERT:
        score += 2

    score = min(score, 10)
    alert["severity_score"] = score
    alert["severity_label"] = (
        "🔴 ÉLEVÉE" if score >= 8 else "🟠 MOYENNE" if score >= 5 else "🟡 FAIBLE"
    )
    alert["recommendation"] = _build_recommendation(alert)
    return alert


def _build_recommendation(alert: dict) -> str:
    outcome = alert.get("outcome") or "?"
    side = alert.get("side") or "BUY"
    price = alert.get("current_price")
    price_str = f"~{price:.2f} ({price * 100:.0f}% implicite)" if price is not None else "inconnu"

    action = "ACHETER" if side == "BUY" else "VENDRE / ÉVITER"
    direction = f"{action} '{outcome}'"

    reasons = []
    if alert["type"] == "CLUSTER":
        reasons.append(f"{len(alert['wallets'])} wallets synchronisés en {alert.get('span_seconds', 0):.0f}s")
        move = alert.get("price_move_pct")
        if move:
            reasons.append(f"prix poussé de {move:+.1f}%")
    else:
        reasons.append("trade isolé anormalement gros")

    rv = alert.get("relative_volume")
    if rv is not None:
        reasons.append(f"{rv * 100:.0f}% du volume 24h du marché")

    reputation = alert.get("wallet_reputation")
    if reputation and reputation.get("checked"):
        fresh = reputation["fresh_count"]
        checked = reputation["checked"]
        if fresh > 0:
            reasons.append(f"{fresh}/{checked} wallets quasi jamais tradé avant (frais)")

    prox = alert.get("proximity_hours")
    if prox is not None:
        if prox < 24:
            reasons.append(f"résolution dans {prox:.0f}h")
        else:
            reasons.append(f"résolution dans {prox / 24:.0f}j")

    return f"{direction} à {price_str}\nPourquoi : {', '.join(reasons)}."
