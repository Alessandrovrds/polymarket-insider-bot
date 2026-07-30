"""
Configuration du bot de détection d'anomalies Polymarket.
Modifie ces valeurs pour ajuster la sensibilité du bot.
"""

# --- Polymarket Data API ---
POLYMARKET_TRADES_URL = "https://data-api.polymarket.com/trades"
POLL_LIMIT = 1000          # nombre de trades récupérés à chaque scan (max 10000)

# --- Fenêtre d'analyse ---
LOOKBACK_MINUTES = 15       # on n'analyse que les trades des X dernières minutes

# --- Détection n°1 : cluster de wallets (plusieurs personnes, même pari, même moment) ---
CLUSTER_WINDOW_SECONDS = 30     # intervalle de temps considéré comme "simultané"
CLUSTER_MIN_WALLETS = 3         # nombre minimum de wallets distincts dans la fenêtre (signal structurel, pas $)
CLUSTER_MIN_TOTAL_USD = 5000    # fallback si le volume 24h du marché est indisponible

# --- Détection n°2 : trade isolé anormalement gros (un seul wallet, grosse mise) ---
SINGLE_TRADE_MIN_USD = 10000    # fallback si le volume 24h du marché est indisponible

# --- Seuils ADAPTATIFS : le seuil $ réel s'ajuste à la taille de chaque marché ---
# effective_threshold = max(FLOOR, PCT * volume24h_du_marché)
# -> un marché à faible volume déclenche plus facilement (mais jamais sous le plancher),
#    un marché énorme (BTC, élections...) a besoin d'un mouvement bien plus gros pour alerter.
ADAPTIVE_THRESHOLDS_ENABLED = True
ADAPTIVE_CLUSTER_PCT_OF_VOLUME24H = 0.05    # cluster >= 5% du volume 24h du marché
ADAPTIVE_WHALE_PCT_OF_VOLUME24H = 0.03      # whale >= 3% du volume 24h du marché
CLUSTER_MIN_TOTAL_USD_FLOOR = 500           # jamais en dessous, même sur un micro marché
SINGLE_TRADE_MIN_USD_FLOOR = 1000

# --- Affinage : métadonnées de marché (Gamma API) ---
GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
RELATIVE_VOLUME_ALERT_RATIO = 0.15   # le trade/cluster pèse >= 15% du volume 24h du marché
PROXIMITY_HOURS_ALERT = 72           # marché qui résout dans moins de 72h = plus suspect
PRICE_MOVE_ALERT_PCT = 5.0           # le cluster a fait bouger le prix de >= 5%

# --- Réputation des wallets (data-api.polymarket.com/traded) ---
WALLET_REPUTATION_ENABLED = True
FRESH_WALLET_MAX_MARKETS = 3        # un wallet ayant tradé <= ce nombre de marchés est "frais"
FRESH_WALLET_RATIO_ALERT = 0.5      # bonus si >= 50% des wallets vérifiés sont frais
MAX_WALLETS_CHECKED_PER_ALERT = 8   # limite d'appels API par alerte (perf + rate limit)

# --- Score de sévérité : seules les alertes >= ce score sont envoyées sur Telegram ---
# 0-4 = faible (ignoré) / 5-7 = moyenne / 8-10 = élevée
MIN_SEVERITY_SCORE = 5

# --- Bot interactif Telegram ---
# GitHub Actions ne tourne que toutes les 5 min : les commandes sont donc traitées
# avec un délai de quelques minutes, pas en instantané (voir amélioration future n°1).
TELEGRAM_GETUPDATES_URL_TMPL = "https://api.telegram.org/bot{token}/getUpdates"
TELEGRAM_SENDMESSAGE_URL_TMPL = "https://api.telegram.org/bot{token}/sendMessage"
DIGEST_THRESHOLD_COUNT = 4          # au-delà de ce nombre d'alertes dans un scan, on groupe en 1 message
DIGEST_TOP_N = 8                    # nombre d'alertes détaillées affichées dans le digest

# --- Anti-doublons / état ---
STATE_FILE = "state.json"
STATE_MAX_AGE_HOURS = 24        # on oublie les alertes plus vieilles que ça

# --- Telegram ---
# Ces valeurs sont lues depuis les variables d'environnement (voir README.md)
# TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID — ne rien mettre en dur ici.
