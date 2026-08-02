"""
Mode TEMPS RÉEL — alternative à scan.py pour qui veut une détection à la
seconde près plutôt qu'un scan toutes les 5 minutes.

⚠️ NE TOURNE PAS SUR GITHUB ACTIONS : ce script maintient une connexion
WebSocket ouverte en continu, ce qu'un job GitHub Actions ne permet pas
(durée de vie limitée, pas de process persistant). Il doit être hébergé sur
un petit serveur toujours actif : VPS (5$/mois), Railway, Fly.io, Render...

Principe :
  1. Connexion à wss://ws-live-data.polymarket.com, abonnement au canal
     "activity/trades" (TOUS les trades de la plateforme, en direct).
  2. Chaque trade reçu est ajouté à un buffer en mémoire (fenêtre glissante
     de REALTIME_BUFFER_MAX_AGE_SECONDS).
  3. Toutes les REALTIME_SCORE_INTERVAL_SECONDS, on relance le même pipeline
     de détection/scoring/notification que scan.py, mais sur le buffer
     mémoire au lieu d'un appel REST — donc sans le délai du polling.
  4. Reconnexion automatique avec backoff en cas de coupure réseau.

Lancement : `python3 realtime_scan.py`
Variables d'environnement requises : TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
(mêmes secrets que pour le mode GitHub Actions).
"""
import asyncio
import json
import sys
import time

import websockets

from config import (
    REALTIME_WS_URL,
    REALTIME_SCORE_INTERVAL_SECONDS,
    REALTIME_BUFFER_MAX_AGE_SECONDS,
    MIN_SEVERITY_SCORE,
    WALLET_REPUTATION_ENABLED,
    NEWS_CHECK_ENABLED,
    FEEDBACK_ENABLED,
)
from detector import detect_anomalies
from state_store import (
    load_state, save_state, filter_new_alerts, is_paused, get_min_severity,
    find_cross_market_wallets, record_wallet_activity,
    find_conflicting_market_signal, record_market_signal,
)
from market_metadata import fetch_market_metadata_batch_cached, build_market_thresholds
from wallet_reputation import assess_wallet_freshness
from news_check import check_recent_news
from scoring import enrich_and_score
from command_handler import process_pending_commands
from telegram_notifier import notify_alerts
from outcome_tracker import record_alert_outcome, review_short_term, review_long_term
from weekly_report import maybe_send_weekly_report

SUBSCRIBE_MESSAGE = {
    "action": "subscribe",
    "subscriptions": [{"topic": "activity", "type": "trades", "filters": ""}],
}


class TradeBuffer:
    """Fenêtre glissante des trades reçus en direct via WebSocket."""

    def __init__(self):
        self._trades: list[dict] = []

    def add(self, payload: dict) -> None:
        try:
            payload = dict(payload)
            payload["usd_value"] = float(payload.get("size", 0)) * float(payload.get("price", 0))
            self._trades.append(payload)
        except (TypeError, ValueError):
            pass  # payload malformé -> on ignore plutôt que de planter le flux

    def snapshot(self) -> list[dict]:
        """Retourne une copie des trades encore dans la fenêtre, et purge les vieux."""
        cutoff = time.time() - REALTIME_BUFFER_MAX_AGE_SECONDS
        self._trades = [t for t in self._trades if t.get("timestamp", 0) >= cutoff]
        return list(self._trades)


async def listen(buffer: TradeBuffer) -> None:
    """Connexion WebSocket avec reconnexion automatique (backoff exponentiel)."""
    backoff = 2
    while True:
        try:
            async with websockets.connect(REALTIME_WS_URL, ping_interval=15, ping_timeout=10) as ws:
                await ws.send(json.dumps(SUBSCRIBE_MESSAGE))
                print("[TEMPS RÉEL] Connecté et abonné au flux de trades.", flush=True)
                backoff = 2  # reset après une connexion réussie

                async for raw_message in ws:
                    try:
                        message = json.loads(raw_message)
                    except json.JSONDecodeError:
                        continue

                    if message.get("topic") == "activity" and message.get("type") == "trades":
                        buffer.add(message.get("payload", {}))

        except Exception as e:
            print(f"[TEMPS RÉEL] Connexion perdue ({e}). Reconnexion dans {backoff}s...", file=sys.stderr, flush=True)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


async def periodic_scan(buffer: TradeBuffer) -> None:
    """Toutes les REALTIME_SCORE_INTERVAL_SECONDS : détection + scoring + notif."""
    state = load_state()

    while True:
        await asyncio.sleep(REALTIME_SCORE_INTERVAL_SECONDS)

        try:
            n_commands = process_pending_commands(state)
            if n_commands:
                print(f"[TEMPS RÉEL] {n_commands} commande(s) Telegram traitée(s).", flush=True)

            if maybe_send_weekly_report(state):
                print("[TEMPS RÉEL] Rapport hebdomadaire envoyé.", flush=True)

            if FEEDBACK_ENABLED:
                review_short_term(state)
                review_long_term(state)

            if is_paused(state):
                save_state(state)
                continue

            trades = buffer.snapshot()
            if not trades:
                continue

            condition_ids = sorted({t.get("conditionId") for t in trades if t.get("conditionId")})
            metadata_by_market = fetch_market_metadata_batch_cached(condition_ids, state)
            market_thresholds = build_market_thresholds(metadata_by_market)

            alerts = detect_anomalies(trades, market_thresholds)
            candidate_alerts = filter_new_alerts(alerts, state)

            min_severity = get_min_severity(state, MIN_SEVERITY_SCORE)
            new_alerts = []
            for alert in candidate_alerts:
                metadata = metadata_by_market.get(alert["conditionId"], {})

                reputation = assess_wallet_freshness(alert["wallets"]) if WALLET_REPUTATION_ENABLED else None
                cross_market_wallets = find_cross_market_wallets(state, alert["wallets"], alert["conditionId"])
                news = check_recent_news(alert.get("title", "")) if NEWS_CHECK_ENABLED else None
                conflicting_signal = find_conflicting_market_signal(
                    state, alert["conditionId"], alert["outcome"], alert["side"]
                )

                scored = enrich_and_score(alert, metadata, reputation, cross_market_wallets, news, conflicting_signal)
                print(
                    f"[TEMPS RÉEL] {scored['type']} sur '{scored.get('title')}' "
                    f"-> score {scored['severity_score']}/10 ({scored['severity_label']})",
                    flush=True,
                )

                record_wallet_activity(state, alert["wallets"], alert["conditionId"])

                if scored["severity_score"] >= min_severity:
                    new_alerts.append(scored)
                    record_market_signal(state, alert["conditionId"], alert["outcome"], alert["side"], scored["severity_score"])

            if new_alerts:
                notify_alerts(new_alerts)
                print(f"[TEMPS RÉEL] {len(new_alerts)} alerte(s) envoyée(s).", flush=True)
                if FEEDBACK_ENABLED:
                    for alert in new_alerts:
                        record_alert_outcome(state, alert)

            save_state(state)

        except Exception as e:
            # une erreur ponctuelle ne doit jamais arrêter le service temps réel
            print(f"[TEMPS RÉEL] Erreur pendant le cycle de scoring : {e}", file=sys.stderr, flush=True)


async def main() -> None:
    buffer = TradeBuffer()
    await asyncio.gather(listen(buffer), periodic_scan(buffer))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[TEMPS RÉEL] Arrêt demandé, fin du service.")
