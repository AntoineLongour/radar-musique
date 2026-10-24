"""
Collecte tes écoutes Spotify.
Spotify ne garde que tes 50 dernières écoutes : GitHub Actions lance ce script toutes les heures
et range chaque nouvelle écoute dans historique/<année>-S<semaine>.json (un fichier par semaine).
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from radar import SPOTIFY_API, appeler_spotify, jeton_spotify   # on réutilise la connexion Spotify du radar

PARIS = ZoneInfo("Europe/Paris")
DOSSIER = Path("historique")


def nom_semaine(moment):
    """Une date -> '2026-S43' (semaine du lundi au dimanche, à l'heure de Paris)."""
    annee, semaine, _ = moment.astimezone(PARIS).isocalendar()
    return f"{annee}-S{semaine:02d}"


def choisir_pochette(images):
    """Spotify donne chaque pochette en plusieurs tailles (640, 300 et 64 px) : on garde celle proche de 300 px."""
    if not images:
        return None
    return min(images, key=lambda image: abs((image.get("width") or 300) - 300))["url"]


def convertir(element):
    """Transforme une écoute renvoyée par Spotify en petit dictionnaire, ou None si ce n'est pas un morceau."""
    piste = element.get("track")
    if not piste:
        return None
    album = piste.get("album") or {}
    return {
        "date": element["played_at"],                     # en UTC, à la milliseconde près
        "titre": piste["name"],
        "id": piste.get("id") or piste["name"],
        "artistes": [artiste["name"] for artiste in piste.get("artists", [])],
        "album": album.get("name"),
        "pochette": choisir_pochette(album.get("images")),
        "lien": (piste.get("external_urls") or {}).get("spotify"),
        "duree_ms": piste.get("duration_ms") or 0,
    }


def main():
    try:
        jeton = jeton_spotify()
        if jeton is None:
            raise SystemExit("Spotify n'est pas configuré : il faut SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET et SPOTIFY_REFRESH_TOKEN.")
        donnees = appeler_spotify(f"{SPOTIFY_API}/me/player/recently-played", jeton, {"limit": 50})
    except requests.RequestException as erreur:
        raise SystemExit(
            f"Spotify a refusé la demande ({erreur}).\n"
            "Si c'est une erreur 400, 401 ou 403 : la clé a expiré ou n'a pas le droit de lire tes écoutes. "
            "Relance spotify_token.py et mets à jour le secret SPOTIFY_REFRESH_TOKEN."
        )

    # range les écoutes reçues par semaine
    par_semaine = {}
    for element in donnees.get("items", []):
        ecoute = convertir(element)
        if ecoute:
            moment = datetime.fromisoformat(ecoute["date"].replace("Z", "+00:00"))
            par_semaine.setdefault(nom_semaine(moment), []).append(ecoute)

    DOSSIER.mkdir(exist_ok=True)
    total_nouvelles = 0
    for semaine, ecoutes in sorted(par_semaine.items()):
        fichier = DOSSIER / f"{semaine}.json"
        deja_la = json.loads(fichier.read_text(encoding="utf-8")) if fichier.exists() else []
        par_date = {e["date"]: e for e in deja_la}       # la date d'écoute sert d'identifiant : pas de doublon
        nouvelles = [e for e in ecoutes if e["date"] not in par_date]
        if not nouvelles:
            continue
        for e in nouvelles:
            par_date[e["date"]] = e
        toutes = sorted(par_date.values(), key=lambda e: e["date"])
        fichier.write_text(json.dumps(toutes, ensure_ascii=False, indent=1), encoding="utf-8")
        total_nouvelles += len(nouvelles)
        print(f"{semaine} : {len(nouvelles)} nouvelle(s) écoute(s), {len(toutes)} au total")

    if total_nouvelles == 0:
        print("Pas de nouvelle écoute depuis la dernière collecte.")


if __name__ == "__main__":
    main()
    