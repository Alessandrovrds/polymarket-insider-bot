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

Quatre affinages supplémentaires (précision + performance) :

- **🚫 Filtre market makers** : les wallets qui tradent en permanence sur
  des dizaines/centaines de marchés (bots de liquidité) sont détectés via
  le même appel `/traded`. Si la majorité des wallets d'une alerte sont des
  market makers, l'alerte est neutralisée — ce n'est pas un insider, juste
  un robot qui fait son travail habituel.
- **🔗 Corrélation multi-marchés** : le bot mémorise (dans `state.json`)
  quels wallets sont apparus dans quelles alertes récemment. Si les mêmes
  wallets réapparaissent sur un AUTRE marché peu après, c'est un signal
  de coordination bien plus fort qu'un cluster isolé — bonus de score.
- **📰 Vérification d'actualité** : avant d'alerter, le bot cherche
  (flux RSS Google News, pas de clé API requise) si une actualité récente
  pourrait expliquer le mouvement. Si oui, ce n'est probablement pas un
  délit d'initié mais une réaction normale à une info publique — le score
  est réduit en conséquence.
- **⚡ Cache + parallélisation** : les métadonnées de marché (volume,
  résolution) sont mises en cache 12 minutes au lieu d'être re-téléchargées
  à chaque scan, et les vérifications de wallets se font en parallèle
  plutôt qu'une par une — scans plus rapides, moins d'appels réseau.

Et pour aller plus loin qu'un scan toutes les 5 minutes : un **mode temps
réel optionnel** (`realtime_scan.py`) branché directement sur le flux
WebSocket de Polymarket — voir la section dédiée plus bas.

Enfin, un **feedback loop** : le bot mémorise chaque alerte envoyée, puis
revient vérifier ce qui s'est réellement passé — le prix a-t-il bougé comme
prévu (court terme), et le marché a-t-il résolu dans le sens suggéré (long
terme) ? Résultat consultable à tout moment via `/stats`, et un **rapport
automatique chaque vendredi**. Voir la section dédiée plus bas.

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
MARKET_MAKER_MIN_MARKETS = 300      # un wallet ayant tradé sur >= 300 marchés = bot de liquidité
MARKET_MAKER_RATIO_VETO = 0.6       # si >= 60% des wallets sont des market makers, alerte écartée

CORRELATION_WINDOW_HOURS = 24       # mémoire pour repérer un wallet déjà vu sur un autre marché
CORRELATION_MIN_WALLETS = 2         # nb de wallets communs pour déclencher le bonus

NEWS_CHECK_ENABLED = True
NEWS_RECENCY_HOURS = 6              # une actu publiée dans les 6h avant l'alerte peut l'expliquer

METADATA_CACHE_TTL_MINUTES = 12     # durée de vie du cache des métadonnées de marché

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
- +3 si des wallets de cette alerte sont déjà apparus sur un AUTRE marché récemment (corrélation)
- -3 si une actualité publique récente pourrait expliquer le mouvement
- **Score forcé à 0** si la majorité des wallets vérifiés sont des market makers connus

## Piloter le bot depuis Telegram

Le bot lit tes messages à chaque scan (délai de quelques minutes, pas
instantané — voir la limite GitHub Actions plus haut) :

| Commande | Effet |
|---|---|
| `/status` | seuil de sévérité actuel, pause en cours |
| `/pause 60` | suspend les alertes pendant 60 minutes |
| `/resume` | annule la pause |
| `/severite 7` | change le seuil de sévérité minimum pour cette session |
| `/stats` | statistiques de fiabilité du bot (voir section Feedback loop) |
| `/aide` | liste des commandes |

## Feedback loop : le bot vérifie ses propres résultats

Après chaque alerte envoyée, le bot mémorise un instantané (prix, wallets,
signaux qui ont déclenché l'alerte), puis revient vérifier ce qui s'est
réellement passé, sur deux horizons :

- **Court terme** (`SHORT_TERM_CHECK_HOURS`, 3h par défaut) : le prix a-t-il
  bougé dans le sens suggéré par l'alerte ? Mesure la réaction immédiate.
- **Long terme** (à la résolution du marché, peut prendre des semaines) :
  l'issue pariée a-t-elle effectivement gagné ? C'est la vraie vérité
  terrain — si le marché n'est pas encore résolu, le bot réessaiera au
  prochain scan (jusqu'à `LONG_TERM_MAX_CHECK_AGE_DAYS`, 60 jours par défaut,
  au-delà de quoi le suivi est abandonné).

Ces vérifications se font automatiquement à chaque scan, en tâche de fond
(jusqu'à `MAX_TRACKED_ALERTS_CHECKED_PER_RUN` alertes vérifiées par passage,
pour ne pas surcharger l'API).

**Consulter les résultats :**
- À tout moment : envoie `/stats` sur Telegram
- Automatiquement chaque **vendredi** : un rapport des 7 derniers jours est
  envoyé sans avoir à le demander (réglable via `WEEKLY_REPORT_ENABLED` et
  `WEEKLY_REPORT_WEEKDAY` dans `config.py`)

Le rapport montre un taux de réussite global (court terme + long terme) et
un détail par signal ("les alertes avec wallets frais ont eu raison X% du
temps") — de quoi juger, avec des vrais chiffres, quels signaux valent la
peine d'être pondérés plus fort dans `scoring.py`.

⚠️ **Il faut du temps avant que ces stats soient utiles.** Les premières
semaines, `/stats` affichera "pas encore assez de données" — c'est normal,
il faut accumuler des dizaines d'alertes avec un résultat connu avant que
les taux de réussite par signal soient statistiquement significatifs.

## Signaux contradictoires : plus jamais deux alertes qui se contredisent en silence

Si le bot t'envoie une alerte "ACHETER Yes" puis, quelques minutes ou
heures après, une autre alerte sur le **même marché** qui pointe dans le
sens opposé (ACHETER No, ou VENDRE Yes), il le détecte automatiquement et
te le dit clairement — au lieu de te laisser deviner que les deux alertes
se contredisent.

Concrètement, dans les `CONTRADICTION_WINDOW_HOURS` (6h par défaut) qui
suivent une alerte envoyée sur un marché, si une nouvelle alerte arrive
dans la direction opposée sur ce même marché :

- Le score de la nouvelle alerte est réduit de `CONTRADICTION_SCORE_PENALTY`
  points (2 par défaut) — deux signaux qui se contredisent inspirent moins
  confiance que chacun pris isolément.
- Le message affiche **en tout premier**, avant même la recommandation
  normale, un avertissement explicite :

  > ⚡ ATTENTION : contredit une alerte envoyée il y a 18 min sur ce même
  > marché (ACHETER 'No', sévérité 6/10). Les deux signaux ne peuvent pas
  > avoir raison en même temps — prudence renforcée.

- Le libellé de sévérité est complété par `⚡ CONTRADICTOIRE` pour que ce
  soit visible d'un coup d'œil, même sans lire tout le message.

Le bot ne choisit pas pour toi lequel des deux signaux croire — il
te donne juste l'information manquante pour trancher toi-même, plutôt que
de recevoir deux alertes qui se contredisent sans lien apparent entre elles.

## Tester en local

```bash
pip install -r requirements.txt
python tests/test_detector.py   # teste la logique de détection (sans réseau)

# Test complet avec la vraie API Polymarket + envoi Telegram réel :
export TELEGRAM_BOT_TOKEN=xxx
export TELEGRAM_CHAT_ID=xxx
python scan.py
```

## Mode temps réel (optionnel)

Le mode par défaut (`scan.py` via GitHub Actions) scanne toutes les 5
minutes. Pour une détection à la seconde près, `realtime_scan.py` se
branche directement sur le flux WebSocket officiel de Polymarket
(`wss://ws-live-data.polymarket.com`, canal `activity/trades` — tous les
trades de la plateforme, en direct, sans limite de fréquence).

⚠️ **Ce script ne peut PAS tourner sur GitHub Actions** : il maintient une
connexion ouverte en permanence, ce qu'un job GitHub Actions ne permet pas
(durée de vie limitée). Il faut l'héberger sur un service qui reste allumé
en continu. Deux options simples :

### Option A — VPS avec systemd (le plus fiable, ~5$/mois)

```bash
# Sur le VPS :
git clone https://github.com/<TON_USER>/<TON_REPO>.git
cd <TON_REPO>
pip install -r requirements.txt --break-system-packages

# Édite deploy/polymarket-realtime.service : chemins + secrets Telegram
sudo cp deploy/polymarket-realtime.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now polymarket-realtime

# Vérifier que ça tourne :
sudo systemctl status polymarket-realtime
sudo journalctl -u polymarket-realtime -f   # logs en direct
```

`Restart=always` dans le fichier service redémarre automatiquement le bot
s'il plante ou si le VPS reboote.

### Option B — Railway / Render (sans gérer de serveur)

Le `Procfile` fourni (`worker: python3 realtime_scan.py`) est reconnu
automatiquement par ces plateformes :

1. Connecte ton repo GitHub sur Railway.app ou Render.com
2. Ajoute les variables d'environnement `TELEGRAM_BOT_TOKEN` et
   `TELEGRAM_CHAT_ID` dans les réglages du service
3. Déploie — la plateforme lance `realtime_scan.py` en continu

### Faire tourner les deux modes en même temps ?

Techniquement oui, mais attention : `scan.py` et `realtime_scan.py` ont
chacun leur propre `state.json` (donc leur propre anti-doublons), ils ne se
coordonnent pas entre eux. Si les deux sont actifs simultanément, tu peux
recevoir la même alerte deux fois. Le plus simple est de choisir UN seul
mode actif à la fois — désactive le workflow GitHub Actions (onglet Actions
→ ⋯ → Disable workflow) si tu passes au temps réel.

## Structure du projet

```
polymarket-insider-bot/
├── config.py              # tous les seuils et réglages (voir ci-dessus)
├── polymarket_client.py   # appel à la Data API Polymarket (trades, mode 5 min)
├── market_metadata.py     # Gamma API : volume/résolution + seuils adaptatifs + cache
├── wallet_reputation.py   # data-api /traded : wallets "frais" + market makers (parallélisé)
├── news_check.py          # flux RSS Google News : vérifie si une actu explique le mouvement
├── detector.py            # logique de détection (cluster + whale)
├── scoring.py             # score de sévérité, veto market maker, bonus corrélation, recommandation
├── command_handler.py     # bot Telegram interactif (/status, /pause, /stats, ...)
├── outcome_tracker.py     # feedback loop : enregistrement + vérif court/long terme + stats
├── weekly_report.py       # rapport hebdomadaire automatique (vendredi)
├── state_store.py         # anti-doublons + overrides + registre de corrélation (state.json)
├── telegram_notifier.py   # formatage + envoi Telegram (individuel ou digest)
├── scan.py                # point d'entrée mode 5 min : orchestre tout le pipeline
├── realtime_scan.py        # point d'entrée mode temps réel (WebSocket, hébergement séparé)
├── deploy/
│   └── polymarket-realtime.service   # exemple de service systemd pour le mode temps réel
├── Procfile                # pour déploiement Railway/Render du mode temps réel
├── state.json              # état persistant (mis à jour automatiquement)
├── requirements.txt
├── tests/                  # tests unitaires (logique pure, sans réseau)
└── .github/workflows/scan.yml
```

## ⚠️ Avertissement

Ce bot repère des **patterns statistiques** (plusieurs wallets synchronisés,
trades anormalement gros). Il ne prouve jamais qu'un délit d'initié a eu
lieu — corrélation n'est pas preuve. Utilise ces alertes comme point de
départ pour ta propre analyse, pas comme un signal d'achat automatique.
Le trading sur marchés de prédiction comporte des risques ; ceci n'est pas
un conseil financier.
