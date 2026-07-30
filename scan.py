"""
Point d'entrée : un scan =
  0. traiter les commandes Telegram en attente (pause/reprise/seuils/statut)
  1. si en pause -> s'arrêter là (mais on a quand même traité les commandes)
  2. récupérer les trades récents
  3. calculer les seuils ADAPTATIFS par marché (métadonnées mises en cache)
  4. détecter les anomalies (cluster + whale) avec ces seuils
  5. filtrer les doublons déjà envoyés
  6. pour chaque candidat : réputation wallet (+ market makers), corrélation
     multi-marchés, vérification d'actualité publique, puis scoring
  7. filtrer par score de sévérité minimum (défaut ou override utilisateur)
  8. notifier Telegram (message unique ou digest si trop d'alertes)
  9. mémoriser les wallets de cette alerte pour la corrélation future

Lancé toutes les 5 minutes par .github/workflows/scan.yml
"""
import sys
from polymarket_client import fetch_recent_trades
from detector import detect_anomalies
from state_store import (
    load_state, save_state, filter_new_alerts, is_paused, get_min_severity,
    find_cross_market_wallets, record_wallet_activity,
)
from telegram_notifier import notify_alerts
from market_metadata import fetch_market_metadata_batch_cached, build_market_thresholds
from wallet_reputation import assess_wallet_freshness
from news_check import check_recent_news
from scoring import enrich_and_score
from command_handler import process_pending_commands
from config import MIN_SEVERITY_SCORE, WALLET_REPUTATION_ENABLED, NEWS_CHECK_ENABLED


def main() -> int:
    state = load_state()

    n_commands = process_pending_commands(state)
    if n_commands:
        print(f"[INFO] {n_commands} commande(s) Telegram traitée(s).")

    if is_paused(state):
        print("[INFO] Bot en pause (voir /resume sur Telegram). Scan ignoré.")
        save_state(state)
        return 0

    try:
        trades = fetch_recent_trades()
    except Exception as e:
        print(f"[ERREUR] Impossible de récupérer les trades Polymarket : {e}", file=sys.stderr)
        save_state(state)
        return 1

    print(f"[INFO] {len(trades)} trades récupérés.")

    # --- Seuils adaptatifs : métadonnées Gamma mises en cache (state.json) ---
    condition_ids = sorted({t.get("conditionId") for t in trades if t.get("conditionId")})
    metadata_by_market = fetch_market_metadata_batch_cached(condition_ids, state)
    market_thresholds = build_market_thresholds(metadata_by_market)
    print(f"[INFO] Seuils adaptatifs calculés pour {len(market_thresholds)} marché(s).")

    alerts = detect_anomalies(trades, market_thresholds)
    print(f"[INFO] {len(alerts)} anomalie(s) détectée(s) avant filtrage doublons.")

    candidate_alerts = filter_new_alerts(alerts, state)
    print(f"[INFO] {len(candidate_alerts)} nouvelle(s) alerte(s) avant scoring.")

    min_severity = get_min_severity(state, MIN_SEVERITY_SCORE)
    new_alerts = []
    for alert in candidate_alerts:
        metadata = metadata_by_market.get(alert["conditionId"], {})

        reputation = None
        if WALLET_REPUTATION_ENABLED:
            reputation = assess_wallet_freshness(alert["wallets"])

        cross_market_wallets = find_cross_market_wallets(state, alert["wallets"], alert["conditionId"])

        news = None
        if NEWS_CHECK_ENABLED:
            news = check_recent_news(alert.get("title", ""))

        scored = enrich_and_score(alert, metadata, reputation, cross_market_wallets, news)
        print(
            f"[INFO] {scored['type']} sur '{scored.get('title')}' "
            f"-> score {scored['severity_score']}/10 ({scored['severity_label']})"
        )

        # on mémorise les wallets pour la corrélation future, même si l'alerte
        # est sous le seuil (le signal reste utile pour un futur cluster ailleurs)
        record_wallet_activity(state, alert["wallets"], alert["conditionId"])

        if scored["severity_score"] >= min_severity:
            new_alerts.append(scored)

    print(f"[INFO] {len(new_alerts)} alerte(s) au-dessus du seuil de sévérité ({min_severity}).")

    if new_alerts:
        try:
            notify_alerts(new_alerts)
        except Exception as e:
            print(f"[ERREUR] Échec de l'envoi Telegram : {e}", file=sys.stderr)
            save_state(state)
            return 1

    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
