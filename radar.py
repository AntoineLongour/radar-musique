"""
Radar musique, étape 1.
Lit artists.txt, trouve chaque artiste sur Deezer
et affiche ses 5 sorties les plus récentes.
"""

import time

import requests

API = "https://api.deezer.com"
PAUSE = 0.2       # secondes d'attente entre deux appels, pour respecter la limite de Deezer
NB_SORTIES = 5    # nombre de sorties à afficher par artiste


def lire_artistes(chemin):
    """Renvoie la liste des artistes du fichier, sans les lignes vides."""
    artistes = []
    with open(chemin, encoding="utf-8") as fichier:
        for ligne in fichier:
            nom = ligne.strip()      # enlève le retour à la ligne et les espaces au bout
            if nom:                  # une ligne vide donne "", que Python considère comme faux
                artistes.append(nom)
    return artistes


def appeler_deezer(url, params=None):
    """Appelle l'API Deezer et renvoie la réponse JSON sous forme de dictionnaire."""
    time.sleep(PAUSE)
    reponse = requests.get(url, params=params, timeout=10)
    reponse.raise_for_status()       # déclenche une erreur si le serveur répond mal (404, 500...)
    donnees = reponse.json()
    if "error" in donnees:           # Deezer signale certaines erreurs dans le JSON lui-même
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
        url = donnees.get("next")    # adresse de la page suivante, absente sur la dernière page
        params = None                # l'adresse "next" contient déjà ses paramètres
    return sorties


def main():
    artistes = lire_artistes("artists.txt")
    print(f"{len(artistes)} artistes à vérifier\n")

    for nom in artistes:
        try:
            trouve = trouver_artiste(nom)
            if trouve is None:
                print(f"✗ {nom} : introuvable sur Deezer\n")
                continue
            artiste_id, nom_deezer = trouve

            sorties = recuperer_sorties(artiste_id)
            # tri de la plus récente à la plus ancienne (les dates AAAA-MM-JJ se trient comme du texte)
            sorties.sort(key=lambda s: s.get("release_date", ""), reverse=True)

            print(f"■ {nom_deezer}")
            if nom_deezer.lower() != nom.lower():
                print(f"   (tu as écrit « {nom} » : vérifie que c'est le bon artiste)")
            for sortie in sorties[:NB_SORTIES]:
                date = sortie.get("release_date", "????-??-??")
                type_sortie = sortie.get("record_type", "?")
                print(f"   {date}  {type_sortie:<8} {sortie['title']}")
            print()

        except (requests.RequestException, RuntimeError) as erreur:
            print(f"✗ {nom} : problème avec Deezer ({erreur})\n")


if __name__ == "__main__":
    main()

    