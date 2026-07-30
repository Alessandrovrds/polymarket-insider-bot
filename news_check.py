"""
Avant d'alerter, on vérifie si une actualité publique récente pourrait
expliquer le mouvement de marché. Si oui, ce n'est probablement pas un
délit d'initié mais une réaction normale à une info publique — on baisse
la sévérité au lieu de crier au loup.

Utilise le flux RSS public de Google News (aucune clé API requise).
"""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote
import xml.etree.ElementTree as ET
import requests
from config import NEWS_CHECK_ENABLED, NEWS_RECENCY_HOURS, NEWS_RSS_URL_TMPL


def _extract_keywords(title: str) -> str:
    """Requête de recherche simplifiée à partir du titre du marché."""
    # on retire la ponctuation la plus bruyante, Google News gère le reste
    cleaned = title.replace("?", "").replace(":", "")
    return cleaned[:120]  # une requête trop longue renvoie souvent 0 résultat


def check_recent_news(market_title: str) -> dict:
    """
    Retourne {"found": bool, "headline": str|None, "checked": bool}.
    `checked=False` si la vérification n'a pas pu être faite (désactivée ou
    erreur réseau) — dans ce cas on ne pénalise ni ne bonifie l'alerte.
    """
    if not NEWS_CHECK_ENABLED or not market_title:
        return {"found": False, "headline": None, "checked": False}

    query = _extract_keywords(market_title)
    url = NEWS_RSS_URL_TMPL.format(query=quote(query))

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception:
        return {"found": False, "headline": None, "checked": False}

    cutoff = datetime.now(timezone.utc).timestamp() - NEWS_RECENCY_HOURS * 3600

    for item in root.findall(".//item"):
        pub_date_str = item.findtext("pubDate")
        if not pub_date_str:
            continue
        try:
            pub_dt = parsedate_to_datetime(pub_date_str)
        except (TypeError, ValueError):
            continue
        if pub_dt.timestamp() >= cutoff:
            headline = item.findtext("title") or None
            return {"found": True, "headline": headline, "checked": True}

    return {"found": False, "headline": None, "checked": True}
