"""
Calcule les résumés « Ma semaine » à partir des écoutes rangées dans Supabase,
et les enregistre dans la table semaines (une ligne par semaine).

Lancé toutes les heures par GitHub, après envoyer_ecoutes.py.
  - La toute première fois (table vide), il calcule TOUTES tes semaines depuis 2019.
  - Ensuite, il ne recalcule que la semaine en cours et la précédente : c'est rapide,
    et ça évite de relire tout l'historique chaque heure.

Les calculs sont ceux de wrapped.py (mêmes chiffres, même format), qu'on réutilise tel quel.
Pour tout recalculer un jour : vide la table semaines dans Supabase, le passage suivant s'en charge.
"""

import json
from datetime import datetime, time, timedelta
from pathlib import Path

from supabase_api import appeler, appeler_fonction, enregistrer, id_du_joueur, lire_tout
from wrapped import PARIS, cle_semaine, compter_artistes, lundi_de, resumer

PSEUDO = "Antoine"                  # ton pseudo sur le site
FICHIER_FILMS = Path("films.json")  # les films restent dans le repo pour l'instant
COLONNES = "ecoute_le,id_spotify,titre,artistes,pochette,lien,duree_ms"


# ---------- Lire les écoutes dans Supabase ----------

def debut_de(cle):
    """'2026-S44' -> le lundi à minuit (heure de Paris), au format attendu par Supabase."""
    return datetime.combine(lundi_de(cle), time(0), tzinfo=PARIS).isoformat()


def ecoutes_entre(joueur, debut=None, fin=None):
    """Les écoutes du joueur entre deux instants (début compris, fin exclue), au format de wrapped.py."""
    params = [("select", COLONNES), ("joueur", f"eq.{joueur}"), ("order", "ecoute_le.asc,id.asc")]
    if debut:
        params.append(("ecoute_le", f"gte.{debut}"))
    if fin:
        params.append(("ecoute_le", f"lt.{fin}"))
    return [
        {
            "date": l["ecoute_le"],
            "titre": l["titre"],
            "id": l["id_spotify"],
            "artistes": l["artistes"] or [],
            "pochette": l["pochette"],
            "lien": l["lien"],
            "duree_ms": l["duree_ms"] or 0,
        }
        for l in lire_tout("ecoutes", params)
    ]


def par_semaine(ecoutes):
    """Range les écoutes par semaine : {'2026-S44': [...], ...}."""
    semaines = {}
    for e in ecoutes:
        moment = datetime.fromisoformat(e["date"]).astimezone(PARIS)
        semaines.setdefault(cle_semaine(moment.date()), []).append(e)
    return semaines


def semaine_avant(cle, semaines=1):
    return cle_semaine(lundi_de(cle) - timedelta(weeks=semaines))


def meme_semaine_l_an_dernier(cle):
    annee, numero = cle.split("-S")
    return f"{int(annee) - 1}-S{numero}"


# ---------- Calculer et enregistrer ----------

def ligne(joueur, cle, resume):
    lundi = lundi_de(cle)
    return {
        "joueur": joueur,
        "semaine": cle,
        "du": lundi.isoformat(),
        "au": (lundi + timedelta(days=6)).isoformat(),
        "resume": resume,
        "mis_a_jour": datetime.now(PARIS).isoformat(timespec="seconds"),
    }


def calculer(cles, semaines, deja_entendus, premiere, films, maintenant):
    """Résume chaque semaine de cles (dans l'ordre), comme wrapped.py."""
    resumes = {}
    for cle in cles:
        ecoutes = semaines.get(cle)
        if not ecoutes:                       # semaine sans écoute : pas de résumé
            continue
        cle_avant = semaine_avant(cle)
        precedente = semaines.get(cle_avant) if cle_avant != premiere else None
        resumes[cle] = resumer(cle, ecoutes, precedente, deja_entendus, maintenant, cle == premiere,
                               semaines, None, films.get(cle))
        deja_entendus = deja_entendus | set(compter_artistes(ecoutes))
    return resumes


def main():
    joueur = id_du_joueur(PSEUDO)
    films = json.loads(FICHIER_FILMS.read_text(encoding="utf-8")) if FICHIER_FILMS.exists() else {}
    maintenant = datetime.now(PARIS)

    tout_premier = appeler("GET", "ecoutes", params={
        "select": "ecoute_le", "joueur": f"eq.{joueur}", "order": "ecoute_le.asc", "limit": 1})
    if not tout_premier:
        print("Aucune écoute dans Supabase pour l'instant.")
        return
    premiere = cle_semaine(datetime.fromisoformat(tout_premier[0]["ecoute_le"]).astimezone(PARIS).date())

    deja_calculees = appeler("GET", "semaines", params={
        "select": "semaine", "joueur": f"eq.{joueur}", "limit": 1})

    if not deja_calculees:
        # Première fois : tout l'historique, de la plus ancienne semaine à la plus récente
        print("Premier calcul : toutes les semaines depuis le début de ton historique…")
        semaines = par_semaine(ecoutes_entre(joueur))
        resumes = calculer(sorted(semaines), semaines, set(), premiere, films, maintenant)
    else:
        # Les autres fois : la semaine en cours et la précédente
        en_cours = cle_semaine(maintenant.date())
        precedente = semaine_avant(en_cours)
        semaines = par_semaine(ecoutes_entre(joueur, debut_de(semaine_avant(en_cours, 2))))
        for cle in (precedente, en_cours):    # pour « Il y a un an »
            avant = meme_semaine_l_an_dernier(cle)
            try:
                debut, fin = debut_de(avant), debut_de(semaine_avant(avant, -1))
            except ValueError:                # semaine 53 qui n'existait pas l'an dernier
                continue
            semaines.update(par_semaine(ecoutes_entre(joueur, debut, fin)))
        deja = set(appeler_fonction("artistes_entendus_avant", {"j": joueur, "avant": debut_de(precedente)}))
        resumes = calculer([precedente, en_cours], semaines, deja, premiere, films, maintenant)

    enregistrer("semaines", [ligne(joueur, cle, r) for cle, r in resumes.items()], "joueur,semaine")

    for cle in sorted(resumes)[-3:]:
        r = resumes[cle]
        numero_un = r["top_artistes"][0]["nom"] if r["top_artistes"] else "-"
        etat = " (en cours)" if r["en_cours"] else ""
        print(f"{cle}{etat} : {r['ecoutes']} écoutes, {r['minutes']} min, n°1 : {numero_un}")
    print(f"{len(resumes)} semaine(s) enregistrée(s) dans Supabase.")


if __name__ == "__main__":
    main()
    