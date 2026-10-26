"""
Choisit chaque semaine un film à la même ambiance que tes musiques.
Une IA gratuite (le modèle gpt-oss-120b, via Groq) reçoit ton top de la semaine et propose un film,
TMDB vérifie que le film existe et fournit l'affiche, et le résultat est rangé dans films.json.
Ce script tourne toutes les heures avec la collecte, mais il ne demande un film que quand il en manque un :
une fois pendant la semaine (film provisoire, dès 15 écoutes), puis une fois la semaine terminée (film définitif).
"""

import json
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import requests

from wrapped import DOSSIER, PARIS, charger_dossier, compter_artistes, lundi_de

ADRESSE_IA = "https://api.groq.com/openai/v1/chat/completions"
MODELES = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]   # si le premier n'est plus proposé, on prend le second
FICHIER_FILMS = Path("films.json")
ECOUTES_MINIMUM = 15     # pas de film provisoire avant 15 écoutes dans la semaine
JOURS_MAX = 14           # pas de film pour les semaines plus anciennes
ESSAIS = 3               # si l'IA propose un film introuvable sur TMDB, on lui redemande (3 fois au maximum)


def ecrire_consigne(ecoutes, a_eviter):
    """Le message envoyé à l'IA : ton top de la semaine et la forme de réponse attendue."""
    artistes = compter_artistes(ecoutes).most_common(10)
    titres = Counter(f"{e['titre']} ({', '.join(e['artistes'])})" for e in ecoutes).most_common(10)

    consigne = (
        "Voici ce que j'ai écouté cette semaine sur Spotify.\n\n"
        "Mes artistes les plus écoutés : " + ", ".join(f"{nom} ({nb} écoutes)" for nom, nb in artistes) + "\n"
        "Mes titres les plus écoutés : " + " ; ".join(f"{titre} ({nb} écoutes)" for titre, nb in titres) + "\n\n"
        "Propose-moi UN film dont l'ambiance correspond à ces musiques : la même énergie, la même émotion, "
        "la même esthétique. Choisis un vrai film qui existe, pas forcément connu, de n'importe quel pays ou époque.\n"
    )
    if a_eviter:
        consigne += "Ne propose aucun de ces films : " + " ; ".join(a_eviter) + "\n"
    consigne += (
        "\nRéponds uniquement avec un objet JSON, sans aucun texte autour, de cette forme :\n"
        '{"titre": "titre en français s\'il existe", "titre_original": "...", "annee": 1999, '
        '"realisateur": "...", "pourquoi": "deux phrases au maximum, en français et en me tutoyant, '
        'qui relient l\'ambiance du film à mes musiques en citant un ou deux de mes artistes"}'
    )
    return consigne


def demander_a_l_ia(cle_api, consigne):
    """Envoie la consigne à l'IA et renvoie le film proposé (un dictionnaire)."""
    for modele in MODELES:
        reponse = requests.post(
            ADRESSE_IA,
            headers={"Authorization": f"Bearer {cle_api}", "Content-Type": "application/json"},
            json={"model": modele, "messages": [{"role": "user", "content": consigne}], "max_completion_tokens": 2000},
            timeout=60,
        )
        if reponse.status_code in (400, 404) and "model" in reponse.text:
            print(f"Le modèle {modele} n'est plus proposé, on essaie le suivant")
            continue
        reponse.raise_for_status()
        texte = reponse.json()["choices"][0]["message"].get("content") or ""

        # on récupère l'objet JSON dans la réponse, même s'il y a du texte autour
        debut, fin = texte.find("{"), texte.rfind("}")
        if debut == -1 or fin == -1:
            raise ValueError(f"réponse inattendue de l'IA : {texte[:200]}")
        film = json.loads(texte[debut:fin + 1])
        if not film.get("titre"):
            raise ValueError("l'IA n'a pas donné de titre")
        return film
    raise ValueError("aucun des modèles n'est disponible : mets à jour la liste MODELES")


def chercher_sur_tmdb(jeton, film):
    """Cherche le film sur TMDB. Renvoie (adresse de l'affiche, lien de la fiche), ou (None, None) si introuvable."""
    recherches = [
        {"query": film.get("titre_original") or film["titre"], "year": film.get("annee")},
        {"query": film["titre"]},
    ]
    for params in recherches:
        reponse = requests.get(
            "https://api.themoviedb.org/3/search/movie",
            headers={"Authorization": f"Bearer {jeton}"},
            params={**params, "language": "fr-FR"},
            timeout=10,
        )
        reponse.raise_for_status()
        resultats = reponse.json().get("results", [])
        if resultats:
            trouve = resultats[0]
            affiche = f"https://image.tmdb.org/t/p/w342{trouve['poster_path']}" if trouve.get("poster_path") else None
            return affiche, f"https://www.themoviedb.org/movie/{trouve['id']}"
    return None, None


def choisir_film(cle, ecoutes, films, cle_api, jeton_tmdb):
    """Demande un film à l'IA et le vérifie sur TMDB. Renvoie (film, affiche, lien), ou None si échec."""
    a_eviter = [f"{f['titre']} ({f.get('annee')})" for c, f in films.items() if c != cle]
    for _ in range(ESSAIS):
        try:
            film = demander_a_l_ia(cle_api, ecrire_consigne(ecoutes, a_eviter))
        except (requests.RequestException, ValueError) as erreur:
            print(f"{cle} : l'IA n'a pas répondu correctement ({erreur})")
            return None
        if not jeton_tmdb:
            return film, None, None          # sans TMDB, on ne peut pas vérifier : on garde la proposition
        try:
            affiche, lien = chercher_sur_tmdb(jeton_tmdb, film)
        except requests.RequestException as erreur:
            print(f"{cle} : TMDB ne répond pas ({erreur}), film gardé sans affiche")
            return film, None, None
        if lien:
            return film, affiche, lien
        # film introuvable : l'IA l'a peut-être inventé, on lui en redemande un autre
        print(f"{cle} : « {film['titre']} » introuvable sur TMDB, on redemande")
        a_eviter.append(f"{film['titre']} ({film.get('annee')})")
    return None


def main():
    films = json.loads(FICHIER_FILMS.read_text(encoding="utf-8")) if FICHIER_FILMS.exists() else {}
    cle_api = os.environ.get("GROQ_API_KEY")
    jeton_tmdb = os.environ.get("TMDB_TOKEN")

    if not cle_api:
        print("Pas de clé GROQ_API_KEY : pas de nouveau film cette fois.")
    else:
        maintenant = datetime.now(PARIS)
        aujourdhui = maintenant.date()
        for cle, ecoutes in sorted(charger_dossier(DOSSIER).items()):
            lundi = lundi_de(cle)
            if lundi < aujourdhui - timedelta(days=JOURS_MAX):
                continue
            terminee = aujourdhui > lundi + timedelta(days=6)
            deja_la = films.get(cle)
            if terminee and deja_la and deja_la.get("definitif"):
                continue                      # le film définitif est déjà choisi
            if not terminee and (deja_la or len(ecoutes) < ECOUTES_MINIMUM):
                continue                      # film provisoire déjà choisi, ou pas encore assez d'écoutes

            resultat = choisir_film(cle, ecoutes, films, cle_api, jeton_tmdb)
            if resultat is None:
                continue
            choix, affiche, lien = resultat
            films[cle] = {
                "titre": choix["titre"],
                "titre_original": choix.get("titre_original"),
                "annee": choix.get("annee"),
                "realisateur": choix.get("realisateur"),
                "pourquoi": choix.get("pourquoi"),
                "affiche": affiche,
                "lien": lien,
                "definitif": terminee,
                "choisi_le": maintenant.isoformat(timespec="minutes"),
            }
            print(f"{cle} : {choix['titre']} ({choix.get('annee')})" + ("" if terminee else ", provisoire"))

    # le fichier existe toujours après ce script, même vide, pour que l'enregistrement git ne plante pas
    FICHIER_FILMS.write_text(json.dumps(films, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
    