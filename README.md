# Polymarket Insider Bot 🕵️

Bot qui scanne en continu les transactions publiques de Polymarket et
t'envoie une alerte Telegram quand il repère un pattern suspect :

- **🚨 Cluster** : plusieurs wallets différents prennent la même position
  (même marché, même issue, même sens) en l'espace de quelques secondes,
  pour un montant cumulé important.
- **🐋 Whale** : un seul wallet place un trade isolé anormalement gros.

Chaque alerte est ensuite **affinée** avec des données de marché (volume 24h,
proximité de la résolution, mouvement de prix provoqué) pour calculer un
**score de sévérité 0-10** — seules les alertes qui dépassent le seuil sont
envoyées, pour éviter le bruit. Chaque notification Telegram contient une
**suggestion de trade concrète** : quoi acheter/vendre, à quel prix, et
pourquoi (les signaux qui ont déclenché l'alerte).

Trois affinages supplémentaires :

- **📏 Seuils adaptatifs** : le seuil en $ n'est plus fixe — il s'ajuste au
  volume 24h de CHAQUE marché. Un trade de 8 000$ est énorme sur un petit
  marché politique obscur, insignifiant sur un marché BTC à 10M$/jour.
- **🕵️ Réputation des wallets** : le bot vérifie sur combien de marchés
  chaque wallet impliqué a déjà tradé (`data-api.polymarket.com/traded`).
  Des wallets "frais" qui n'ont presque jamais tradé et qui apparaissent
  soudain, synchronisés, sont un signal d'insider plus fort.
- **🤖 Bot interactif** : commandes Telegram `/status`, `/pause <min>`,
  `/resume`, `/severite <0-10>`, `/aide` pour piloter le bot depuis ton
  téléphone. Si plusieurs alertes arrivent dans le même scan, elles sont
  groupées en un seul message digest pour éviter le spam.

Le bot n'exécute **aucun ordre** — il t'alerte seulement, tu trades toi-même.

## Comment ça marche

Un [workflow GitHub Actions](.github/workflows/scan.yml) tourne toutes les
5 minutes (le minimum autorisé par GitHub), interroge l'API publique de
Polymarket (`data-api.polymarket.com/trades`), fait tourner la détection,
et pousse les alertes sur Telegram. Aucun serveur à gérer.

⚠️ Limite à connaître : GitHub Actions ne permet pas d'aller plus vite que
5 minutes entre deux scans (et peut retarder un peu plus en cas de forte
charge sur GitHub). Ce n'est donc pas du "temps réel à la seconde" — mais
comme le bot ré-analyse une fenêtre de 15 minutes à chaque passage
(`LOOKBACK_MINUTES` dans `config.py`), il détecte quand même les clusters
qui se sont formés en quelques secondes, avec un délai de quelques minutes
avant l'alerte. Si tu veux du vrai temps réel plus tard, il faudra héberger
le script en continu sur un petit serveur (VPS) au lieu de GitHub Actions.

## Installation

### 1. Créer le bot Telegram

1. Ouvre Telegram, cherche **@BotFather**, envoie `/newbot` et suis les
   instructions. Tu obtiens un **token** du type `123456:ABC-DEF...`.
2. Démarre une conversation avec ton nouveau bot (clique "Start").
3. Récupère ton **chat_id** : envoie n'importe quel message à ton bot, puis
   va sur `https://api.telegram.org/bot<TON_TOKEN>/getUpdates` dans un
   navigateur. Le champ `"chat":{"id": ...}` contient ton chat_id.

### 2. Créer le repo GitHub

1. Crée un nouveau repo (public ou privé) sur GitHub.
2. Pousse ces fichiers dedans :

```bash
git init
git add .
git commit -m "Initial commit: Polymarket insider bot"
git branch -M main
git remote add origin https://github.com/<TON_USER>/<TON_REPO>.git
git push -u origin main
```

### 3. Configurer les secrets

Dans le repo GitHub : **Settings → Secrets and variables → Actions → New
repository secret**, ajoute :

| Nom | Valeur |
|---|---|
| `TELEGRAM_BOT_TOKEN` | le token donné par @BotFather |
| `TELEGRAM_CHAT_ID` | ton chat_id |

### 4. Activer les Actions

Va dans l'onglet **Actions** du repo, active les workflows si demandé. Le
scan se lance automatiquement toutes les 5 minutes. Tu peux aussi le
déclencher manuellement via **Actions → Scan Polymarket → Run workflow**
pour vérifier que tout fonctionne.

## Ajuster la sensibilité

Tout se règle dans [`config.py`](config.py) :

```python
CLUSTER_WINDOW_SECONDS = 30     # fenêtre "simultanée"
CLUSTER_MIN_WALLETS = 3         # nb de wallets distincts minimum (signal structurel)

ADAPTIVE_THRESHOLDS_ENABLED = True
ADAPTIVE_CLUSTER_PCT_OF_VOLUME24H = 0.05    # cluster >= 5% du volume 24h du marché
ADAPTIVE_WHALE_PCT_OF_VOLUME24H = 0.03      # whale >= 3% du volume 24h du marché
CLUSTER_MIN_TOTAL_USD_FLOOR = 500           # plancher absolu même sur un micro marché
SINGLE_TRADE_MIN_USD_FLOOR = 1000

RELATIVE_VOLUME_ALERT_RATIO = 0.15   # bonus de score si le trade pèse >= 15% du volume 24h
PROXIMITY_HOURS_ALERT = 72           # bonus si le marché résout dans < 72h
PRICE_MOVE_ALERT_PCT = 5.0           # bonus si le cluster a fait bouger le prix de >= 5%

WALLET_REPUTATION_ENABLED = True
FRESH_WALLET_MAX_MARKETS = 3        # un wallet ayant tradé <= 3 marchés est "frais"
FRESH_WALLET_RATIO_ALERT = 0.5      # bonus si >= 50% des wallets vérifiés sont frais

MIN_SEVERITY_SCORE = 5   # seules les alertes >= ce score sont envoyées (5-7 = moyenne, 8-10 = élevée)
DIGEST_THRESHOLD_COUNT = 4   # au-delà de 4 alertes dans un scan, on groupe en 1 message
```

Si tu reçois trop d'alertes non pertinentes, monte `MIN_SEVERITY_SCORE` (ou
envoie `/severite 7` sur Telegram pour ajuster sans toucher au code). Si tu
n'en reçois pas assez, baisse-le.

**Comment le score est calculé** (0 à 10) :
- +2 de base (l'alerte a déjà passé les seuils de détection)
- +2 si le cluster a 2x plus de wallets que le minimum, ou +4 si le whale a 2x le montant minimum
- +2 si le montant cumulé du cluster est 3x le minimum
- +2 si le prix a bougé de plus de `PRICE_MOVE_ALERT_PCT`
- +2 si le trade/cluster pèse plus de `RELATIVE_VOLUME_ALERT_RATIO` du volume 24h du marché
- +2 si le marché résout dans moins de `PROXIMITY_HOURS_ALERT` heures
- +2 si `FRESH_WALLET_RATIO_ALERT` ou plus des wallets vérifiés sont "frais"

## Piloter le bot depuis Telegram

Le bot lit tes messages à chaque scan (délai de quelques minutes, pas
instantané — voir la limite GitHub Actions plus haut) :

| Commande | Effet |
|---|---|
| `/status` | seuil de sévérité actuel, pause en cours |
| `/pause 60` | suspend les alertes pendant 60 minutes |
| `/resume` | annule la pause |
| `/severite 7` | change le seuil de sévérité minimum pour cette session |
| `/aide` | liste des commandes |

## Tester en local

```bash
pip install -r requirements.txt
python tests/test_detector.py   # teste la logique de détection (sans réseau)

# Test complet avec la vraie API Polymarket + envoi Telegram réel :
export TELEGRAM_BOT_TOKEN=xxx
export TELEGRAM_CHAT_ID=xxx
python scan.py
```

## Structure du projet

```
polymarket-insider-bot/
├── config.py              # seuils de détection, adaptatifs, réputation, digest
├── polymarket_client.py   # appel à la Data API Polymarket (trades)
├── market_metadata.py     # Gamma API : volume/résolution + seuils adaptatifs
├── wallet_reputation.py   # data-api /traded : détection des wallets "frais"
├── detector.py            # logique de détection (cluster + whale)
├── scoring.py             # score de sévérité + recommandation de trade
├── command_handler.py     # bot Telegram interactif (/status, /pause, ...)
├── state_store.py         # anti-doublons + overrides persistants (state.json)
├── telegram_notifier.py   # formatage + envoi Telegram (individuel ou digest)
├── scan.py                # point d'entrée : orchestre tout le pipeline
├── state.json             # état persistant (mis à jour automatiquement)
├── requirements.txt
├── tests/                 # tests unitaires (logique pure, sans réseau)
└── .github/workflows/scan.yml
```

## ⚠️ Avertissement

Ce bot repère des **patterns statistiques** (plusieurs wallets synchronisés,
trades anormalement gros). Il ne prouve jamais qu'un délit d'initié a eu
lieu — corrélation n'est pas preuve. Utilise ces alertes comme point de
départ pour ta propre analyse, pas comme un signal d'achat automatique.
Le trading sur marchés de prédiction comporte des risques ; ceci n'est pas
un conseil financier.
