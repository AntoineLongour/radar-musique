"""
Radar musique, étape 5.
Récupère tes artistes sur Spotify (les plus écoutés + ceux que tu suis),
ajoute ceux de artists.txt, cherche leurs sorties des 7 derniers jours sur Deezer
et les enregistre dans releases.json.
"""

import json
import os
import re
import time
import unicodedata
import urllib.parse
from datetime import date, datetime, timedelta, timezone

import requests

API = "https://api.deezer.com"
SPOTIFY_API = "https://api.spotify.com/v1"
PAUSE = 0.2                  # secondes d'attente entre deux appels à Deezer, pour respecter sa limite
JOURS = 7                    # on garde les sorties des 7 derniers jours
FICHIER_SORTIE = "releases.json"

# Quand une même sortie existe en plusieurs versions, on garde le type le plus important
PRIORITE_TYPE = {"album": 0, "ep": 1, "single": 2, "compile": 3}


# ---------- Outils ----------

def normaliser(nom):
    """'La Fève ' -> 'la feve' : pour comparer des noms sans se soucier des accents, majuscules et ponctuation."""
    sans_accents = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", sans_accents.lower()).strip()


def lire_artistes(chemin):
    """Renvoie la liste des artistes du fichier, sans les lignes vides."""
    artistes = []
    with open(chemin, encoding="utf-8") as fichier:
        for ligne in fichier:
            nom = ligne.strip()
            if nom:
                artistes.append(nom)
    return artistes


def lire_date(texte):
    """Transforme '2026-10-23' en date Python. Renvoie None si la date est absente ou invalide."""
    try:
        return date.fromisoformat(texte)
    except (TypeError, ValueError):
        return None


# ---------- Spotify : qui écoutes-tu ? ----------

def jeton_spotify():
    """Échange la clé longue durée contre un jeton valable une heure. Renvoie None si Spotify n'est pas configuré."""
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    refresh_token = os.environ.get("SPOTIFY_REFRESH_TOKEN")
    if not (client_id and client_secret and refresh_token):
        return None
    reponse = requests.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        auth=(client_id, client_secret),
        timeout=10,
    )
    reponse.raise_for_status()
    return reponse.json()["access_token"]


def appeler_spotify(url, jeton, params=None):
    """Appelle l'API Spotify. Attend et réessaie une fois si Spotify demande de ralentir (erreur 429)."""
    for _ in range(2):
        reponse = requests.get(url, headers={"Authorization": f"Bearer {jeton}"}, params=params, timeout=10)
        if reponse.status_code == 429:
            time.sleep(min(int(reponse.headers.get("Retry-After", "5")), 30))
            continue
        reponse.raise_for_status()
        return reponse.json()
    reponse.raise_for_status()


def artistes_spotify(jeton):
    """Tes artistes les plus écoutés (4 dernières semaines et 6 derniers mois) + ceux que tu suis."""
    noms = []
    for periode in ("short_term", "medium_term"):
        donnees = appeler_spotify(f"{SPOTIFY_API}/me/top/artists", jeton, {"time_range": periode, "limit": 50})
        noms += [artiste["name"] for artiste in donnees.get("items", [])]

    url = f"{SPOTIFY_API}/me/following"
    params = {"type": "artist", "limit": 50}
    while url:
        donnees = appeler_spotify(url, jeton, params)["artists"]
        noms += [artiste["name"] for artiste in donnees.get("items", [])]
        url = donnees.get("next")    # page suivante, absente sur la dernière page
        params = None                # l'adresse "next" contient déjà ses paramètres
    return noms


def construire_liste():
    """Liste finale des artistes, sans doublons. Renvoie (noms, état de Spotify)."""
    noms = lire_artistes("artists.txt")   # tes ajouts à la main, toujours pris en compte
    etat = "absent"
    try:
        jeton = jeton_spotify()
        if jeton:
            noms += artistes_spotify(jeton)
            etat = "ok"
        else:
            print("Spotify n'est pas configuré : seule la liste artists.txt est utilisée.")
    except requests.RequestException as erreur:
        etat = "erreur"
        print(f"⚠ Spotify ne répond pas ou la clé a expiré ({erreur}). Seule la liste artists.txt est utilisée.")

    uniques, deja_vus = [], set()
    for nom in noms:
        cle = normaliser(nom)
        if cle and cle not in deja_vus:
            deja_vus.add(cle)
            uniques.append(nom)
    return uniques, etat


# ---------- Deezer : quoi de neuf ? ----------

def appeler_deezer(url, params=None):
    """Appelle l'API Deezer et renvoie la réponse JSON sous forme de dictionnaire."""
    time.sleep(PAUSE)
    reponse = requests.get(url, params=params, timeout=10)
    reponse.raise_for_status()
    donnees = reponse.json()
    if "error" in donnees:
        raise RuntimeError(donnees["error"].get("message", "erreur Deezer"))
    return donnees


def trouver_artiste(nom):
    """Cherche l'artiste sur Deezer et ne garde qu'un nom identique, pour éviter les homonymes.
    Renvoie (identifiant, nom trouvé), ou None."""
    donnees = appeler_deezer(f"{API}/search/artist", params={"q": nom, "limit": 5})
    for resultat in donnees.get("data", []):
        if normaliser(resultat["name"]) == normaliser(nom):
            return resultat["id"], resultat["name"]
    return None


def recuperer_sorties(artiste_id):
    """Renvoie toutes les sorties de l'artiste, en parcourant toutes les pages."""
    sorties = []
    url = f"{API}/artist/{artiste_id}/albums"
    params = {"limit": 100}
    while url:
        donnees = appeler_deezer(url, params=params)
        sorties.extend(donnees.get("data", []))
        url = donnees.get("next")
        params = None
    return sorties


# ---------- Programme principal ----------

def main():
    aujourdhui = date.today()
    debut = aujourdhui - timedelta(days=JOURS)

    artistes, etat_spotify = construire_liste()
    print(f"{len(artistes)} artistes à vérifier, sorties depuis le {debut:%d/%m/%Y}\n")

    nouveautes = {}     # clé : identifiant Deezer de la sortie, pour éviter les doublons (featurings)
    introuvables = []

    for nom in artistes:
        try:
            trouve = trouver_artiste(nom)
            if trouve is None:
                introuvables.append(nom)
                continue
            artiste_id, nom_deezer = trouve

            recentes = []
            for sortie in recuperer_sorties(artiste_id):
                date_sortie = lire_date(sortie.get("release_date"))
                if date_sortie and debut <= date_sortie <= aujourdhui:
                    recentes.append(sortie)

            # même titre en plusieurs versions (explicite, deluxe...) : on n'en garde qu'une
            par_titre = {}
            for sortie in recentes:
                titre = sortie["title"].strip().lower()
                deja_la = par_titre.get(titre)
                if deja_la is None or PRIORITE_TYPE.get(sortie.get("record_type"), 9) < PRIORITE_TYPE.get(deja_la.get("record_type"), 9):
                    par_titre[titre] = sortie

            # singles extraits d'un album ou EP de la même semaine (même pochette) : on ne garde que l'album
            pochettes_albums = {s.get("md5_image") for s in par_titre.values()
                                if s.get("record_type") in ("album", "ep") and s.get("md5_image")}
            par_titre = {t: s for t, s in par_titre.items()
                         if s.get("record_type") in ("album", "ep") or s.get("md5_image") not in pochettes_albums}

            for sortie in par_titre.values():
                if sortie["id"] in nouveautes:
                    # la sortie est déjà là via un autre artiste de ta liste (featuring) : on ajoute son nom
                    if nom_deezer not in nouveautes[sortie["id"]]["artistes"]:
                        nouveautes[sortie["id"]]["artistes"].append(nom_deezer)
                    continue
                recherche = urllib.parse.quote(f"{nom_deezer} {sortie['title']}")
                nouveautes[sortie["id"]] = {
                    "artistes": [nom_deezer],
                    "titre": sortie["title"],
                    "type": sortie.get("record_type", "?"),
                    "date": sortie["release_date"],
                    "pochette": sortie.get("cover_medium"),
                    "lien": sortie.get("link"),
                    "spotify": f"https://open.spotify.com/search/{recherche}",
                }

            if par_titre:
                print(f"✓ {nom_deezer} : {len(par_titre)} sortie(s)")

        except (requests.RequestException, RuntimeError) as erreur:
            print(f"✗ {nom} : problème avec Deezer ({erreur})")

    if introuvables:
        print(f"\nPas trouvés sur Deezer avec exactement le même nom ({len(introuvables)}) : {', '.join(introuvables)}")

    # liste finale, de la plus récente à la plus ancienne
    sorties_finales = sorted(nouveautes.values(), key=lambda s: s["date"], reverse=True)

    resultat = {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "depuis": debut.isoformat(),
        "jusqua": aujourdhui.isoformat(),
        "spotify": etat_spotify,
        "nb_artistes": len(artistes),
        "sorties": sorties_finales,
    }
    with open(FICHIER_SORTIE, "w", encoding="utf-8") as fichier:
        json.dump(resultat, fichier, ensure_ascii=False, indent=2)

    print(f"\n{len(sorties_finales)} nouveauté(s) enregistrée(s) dans {FICHIER_SORTIE}\n")
    for s in sorties_finales:
        print(f"   {s['date']}  {s['type']:<8} {', '.join(s['artistes'])} : {s['titre']}")


if __name__ == "__main__":
    main()