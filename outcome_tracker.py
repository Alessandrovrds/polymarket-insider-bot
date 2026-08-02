"""
Feedback loop : enregistre chaque alerte envoyée, puis revient vérifier ce
qui s'est réellement passé, sur deux horizons :

- COURT TERME (quelques heures après) : le prix a-t-il bougé dans le sens
  suggéré par l'alerte ? Mesure la réaction immédiate du marché.
- LONG TERME (à la résolution du marché) : l'issue pariée a-t-elle
  effectivement gagné ? C'est la vraie vérité terrain.

Les résultats sont stockés dans state.json :
  - state["tracked_alerts"]  : alertes en attente de vérification
  - state["alert_history"]   : alertes archivées une fois complètement vérifiées
                                (ou abandonnées après LONG_TERM_MAX_CHECK_AGE_DAYS)

get_stats() calcule des taux de réussite globaux et par signal, utilisés par
la commande /stats et le rapport hebdomadaire automatique.
"""
import time
from config import (
    SHORT_TERM_CHECK_HOURS,
    LONG_TERM_MAX_CHECK_AGE_DAYS,
    MAX_TRACKED_ALERTS_CHECKED_PER_RUN,
    ALERT_HISTORY_MAX_ENTRIES,
    FRESH_WALLET_RATIO_ALERT,
)
from market_metadata import fetch_current_outcome_price, fetch_market_resolution


def _extract_signals(alert: dict) -> dict:
    """Capture les signaux actifs au moment de l'alerte, pour l'analyse par signal plus tard."""
    reputation = alert.get("wallet_reputation") or {}
    fresh_ratio = reputation.get("fresh_ratio")
    news = alert.get("news") or {}
    return {
        "type": alert.get("type"),
        "fresh_wallets": bool(fresh_ratio is not None and fresh_ratio >= FRESH_WALLET_RATIO_ALERT),
        "cross_market": bool(alert.get("cross_market_wallets")),
        "news_found": bool(news.get("found")),
        "adaptive_threshold": bool(alert.get("adaptive")),
    }


def record_alert_outcome(state: dict, alert: dict) -> None:
    """Appelé juste après l'envoi d'une alerte : on mémorise un instantané à vérifier plus tard."""
    tracked = state.setdefault("tracked_alerts", {})
    tracked[alert["key"]] = {
        "key": alert["key"],
        "type": alert.get("type"),
        "conditionId": alert.get("conditionId"),
        "title": alert.get("title"),
        "outcome": alert.get("outcome"),
        "outcomeIndex": alert.get("outcomeIndex"),
        "side": alert.get("side"),
        "price_at_alert": alert.get("current_price"),
        "severity_score": alert.get("severity_score"),
        "signals": _extract_signals(alert),
        "sent_at": time.time(),
        "short_term": None,
        "long_term": None,
    }


def _archive_if_done(state: dict, key: str) -> None:
    """Déplace une alerte entièrement vérifiée (ou abandonnée) vers l'historique compact."""
    tracked = state.setdefault("tracked_alerts", {})
    history = state.setdefault("alert_history", [])
    entry = tracked.get(key)
    if not entry:
        return

    short_done = entry["short_term"] is not None
    long_done = entry["long_term"] is not None
    timed_out = (time.time() - entry["sent_at"]) > LONG_TERM_MAX_CHECK_AGE_DAYS * 86400

    if (short_done and long_done) or timed_out:
        if timed_out and not long_done:
            entry["long_term"] = {"checked_at": time.time(), "resolved": False, "correct": None}
        history.append(entry)
        del tracked[key]

    # borne la taille de l'historique (on garde les plus récents)
    if len(history) > ALERT_HISTORY_MAX_ENTRIES:
        state["alert_history"] = history[-ALERT_HISTORY_MAX_ENTRIES:]


def review_short_term(state: dict) -> int:
    """Vérifie le prix des alertes assez anciennes pour être jugées à court terme. Retourne le nb vérifié."""
    tracked = state.setdefault("tracked_alerts", {})
    now = time.time()
    checked = 0

    for key, entry in list(tracked.items()):
        if checked >= MAX_TRACKED_ALERTS_CHECKED_PER_RUN:
            break
        if entry["short_term"] is not None:
            continue
        if (now - entry["sent_at"]) < SHORT_TERM_CHECK_HOURS * 3600:
            continue

        price_now = fetch_current_outcome_price(entry["conditionId"], entry.get("outcomeIndex"))
        checked += 1

        if price_now is None:
            # marché introuvable ou données indisponibles -> on abandonne ce suivi précis
            entry["short_term"] = {"checked_at": now, "price_then": None, "price_now": None, "correct": None}
        else:
            price_then = entry.get("price_at_alert")
            correct = None
            if price_then:
                moved_up = price_now > price_then
                correct = moved_up if entry["side"] == "BUY" else (not moved_up)
            entry["short_term"] = {
                "checked_at": now,
                "price_then": price_then,
                "price_now": price_now,
                "correct": correct,
            }

        _archive_if_done(state, key)

    return checked


def review_long_term(state: dict) -> int:
    """Vérifie la résolution des marchés des alertes en attente. Retourne le nb vérifié."""
    tracked = state.setdefault("tracked_alerts", {})
    now = time.time()
    checked = 0

    for key, entry in list(tracked.items()):
        if checked >= MAX_TRACKED_ALERTS_CHECKED_PER_RUN:
            break
        if entry["long_term"] is not None:
            continue

        resolution = fetch_market_resolution(entry["conditionId"])
        checked += 1

        if resolution["closed"]:
            winning_index = resolution["winning_outcome_index"]
            correct = None
            if winning_index is not None and entry.get("outcomeIndex") is not None:
                predicted_win = entry["side"] == "BUY"
                actual_win = winning_index == entry["outcomeIndex"]
                correct = predicted_win == actual_win
            entry["long_term"] = {"checked_at": now, "resolved": True, "correct": correct}
            _archive_if_done(state, key)
        # sinon : marché pas encore résolu, on retentera au prochain scan
        # (sauf abandon automatique après LONG_TERM_MAX_CHECK_AGE_DAYS, géré par _archive_if_done)

    return checked


def get_stats(state: dict, since_ts: float | None = None) -> dict:
    """
    Agrège les résultats connus (historique archivé + alertes déjà vérifiées
    en attente) en statistiques globales et par signal.
    """
    all_entries = list(state.get("alert_history", [])) + list(state.get("tracked_alerts", {}).values())
    if since_ts:
        all_entries = [e for e in all_entries if e.get("sent_at", 0) >= since_ts]

    def _win_rate(entries: list[dict], horizon: str) -> tuple[float | None, int, int]:
        results = [e[horizon]["correct"] for e in entries if e.get(horizon) and e[horizon].get("correct") is not None]
        if not results:
            return None, 0, len(results)
        wins = sum(1 for r in results if r)
        return wins / len(results), wins, len(results)

    stats = {
        "total_alerts": len(all_entries),
        "short_term": {},
        "long_term": {},
        "by_signal": {},
    }

    st_rate, st_wins, st_n = _win_rate(all_entries, "short_term")
    lt_rate, lt_wins, lt_n = _win_rate(all_entries, "long_term")
    stats["short_term"] = {"win_rate": st_rate, "wins": st_wins, "n": st_n}
    stats["long_term"] = {"win_rate": lt_rate, "wins": lt_wins, "n": lt_n}

    for signal_name in ("fresh_wallets", "cross_market", "news_found"):
        with_signal = [e for e in all_entries if e.get("signals", {}).get(signal_name)]
        rate_with, wins_with, n_with = _win_rate(with_signal, "long_term")
        stats["by_signal"][signal_name] = {
            "win_rate_with": rate_with, "n_with": n_with,
        }

    return stats


def format_stats_message(stats: dict, title: str = "STATISTIQUES DU BOT") -> str:
    lines = [f"📊 {title}\n"]
    lines.append(f"Alertes suivies : {stats['total_alerts']}")

    st = stats["short_term"]
    if st["n"]:
        lines.append(f"Court terme (prix a bougé comme prévu) : {st['win_rate'] * 100:.0f}% ({st['wins']}/{st['n']})")
    else:
        lines.append("Court terme : pas encore assez de données")

    lt = stats["long_term"]
    if lt["n"]:
        lines.append(f"Long terme (résolution du marché) : {lt['win_rate'] * 100:.0f}% ({lt['wins']}/{lt['n']})")
    else:
        lines.append("Long terme : pas encore de marché résolu à analyser")

    labels = {
        "fresh_wallets": "Wallets frais",
        "cross_market": "Corrélation multi-marchés",
        "news_found": "Actualité détectée",
    }
    signal_lines = []
    for key, label in labels.items():
        s = stats["by_signal"].get(key, {})
        if s.get("n_with"):
            signal_lines.append(f"  • {label} présent : {s['win_rate_with'] * 100:.0f}% ({s['n_with']} alertes)")

    if signal_lines:
        lines.append("\nPar signal (long terme) :")
        lines.extend(signal_lines)

    return "\n".join(lines)
