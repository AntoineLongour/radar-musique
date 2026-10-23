"""
Radar musique, étape 2.
Lit artists.txt, récupère les sorties de chaque artiste sur Deezer,
garde celles des 7 derniers jours et les enregistre dans releases.json.
"""

import json
import time
from datetime import date, datetime, timedelta, timezone

import requests

API = "https://api.deezer.com"
PAUSE = 0.2                  # secondes d'attente entre deux appels, pour respecter la limite de Deezer
JOURS = 7                    # on garde les sorties des 7 derniers jours
FICHIER_SORTIE = "releases.json"

# Quand une même sortie existe en plusieurs versions, on garde le type le plus important
PRIORITE_TYPE = {"album": 0, "ep": 1, "single": 2, "compile": 3}


def lire_artistes(chemin):
    """Renvoie la liste des artistes du fichier, sans les lignes vides."""
    artistes = []
    with open(chemin, encoding="utf-8") as fichier:
        for ligne in fichier:
            nom = ligne.strip()
            if nom:
                artistes.append(nom)
    return artistes


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
    """Cherche l'artiste sur Deezer. Renvoie (identifiant, nom trouvé), ou None si rien."""
    donnees = appeler_deezer(f"{API}/search/artist", params={"q": nom, "limit": 1})
    resultats = donnees.get("data", [])
    if not resultats:
        return None
    premier = resultats[0]
    return premier["id"], premier["name"]


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


def lire_date(texte):
    """Transforme '2026-10-23' en date Python. Renvoie None si la date est absente ou invalide."""
    try:
        return date.fromisoformat(texte)
    except (TypeError, ValueError):
        return None


def main():
    aujourdhui = date.today()
    debut = aujourdhui - timedelta(days=JOURS)

    artistes = lire_artistes("artists.txt")
    print(f"{len(artistes)} artistes à vérifier, sorties depuis le {debut:%d/%m/%Y}\n")

    nouveautes = {}   # clé : identifiant Deezer de la sortie, pour éviter les doublons (featurings)

    for nom in artistes:
        try:
            trouve = trouver_artiste(nom)
            if trouve is None:
                print(f"✗ {nom} : introuvable sur Deezer")
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
                nouveautes[sortie["id"]] = {
                    "artistes": [nom_deezer],
                    "titre": sortie["title"],
                    "type": sortie.get("record_type", "?"),
                    "date": sortie["release_date"],
                    "pochette": sortie.get("cover_medium"),
                    "lien": sortie.get("link"),
                }

            print(f"✓ {nom_deezer} : {len(par_titre)} sortie(s)")

        except (requests.RequestException, RuntimeError) as erreur:
            print(f"✗ {nom} : problème avec Deezer ({erreur})")

    # liste finale, de la plus récente à la plus ancienne
    sorties_finales = sorted(nouveautes.values(), key=lambda s: s["date"], reverse=True)

    resultat = {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "depuis": debut.isoformat(),
        "jusqua": aujourdhui.isoformat(),
        "sorties": sorties_finales,
    }
    with open(FICHIER_SORTIE, "w", encoding="utf-8") as fichier:
        json.dump(resultat, fichier, ensure_ascii=False, indent=2)

    print(f"\n{len(sorties_finales)} nouveauté(s) enregistrée(s) dans {FICHIER_SORTIE}\n")
    for s in sorties_finales:
        print(f"   {s['date']}  {s['type']:<8} {', '.join(s['artistes'])} : {s['titre']}")


if __name__ == "__main__":
    main()
