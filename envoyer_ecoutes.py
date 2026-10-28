"""
Envoie les écoutes du dossier historique/ dans Supabase (table ecoutes), sur ton compte.

Lancé toutes les heures par GitHub, après ecoutes.py.
On renvoie tout le dossier à chaque passage : Supabase ignore les écoutes déjà enregistrées
(même compte, même date), donc rien n'est jamais en double, et un passage raté est rattrapé au suivant.
"""

import json
from pathlib import Path

from supabase_api import ajouter_nouvelles, id_du_joueur

PSEUDO = "Antoine"            # ton pseudo sur le site
DOSSIER = Path("historique")


def convertir(ecoute, joueur):
    """Une écoute de historique/ -> une ligne de la table ecoutes."""
    return {
        "joueur": joueur,
        "ecoute_le": ecoute["date"],
        "id_spotify": ecoute.get("id"),
        "titre": ecoute["titre"],
        "artistes": ecoute.get("artistes") or [],
        "album": ecoute.get("album"),
        "pochette": ecoute.get("pochette"),
        "lien": ecoute.get("lien"),
        "duree_ms": ecoute.get("duree_ms"),
        "source": ecoute.get("source", "spotify"),
    }


def main():
    joueur = id_du_joueur(PSEUDO)

    par_date = {}   # une seule écoute par date, comme dans Supabase
    for fichier in sorted(DOSSIER.glob("*.json")):
        for ecoute in json.loads(fichier.read_text(encoding="utf-8")):
            par_date[ecoute["date"]] = convertir(ecoute, joueur)

    lignes = sorted(par_date.values(), key=lambda l: l["ecoute_le"])
    ajoutees = ajouter_nouvelles("ecoutes", lignes, "joueur,ecoute_le")
    print(f"{ajoutees} nouvelle(s) écoute(s) envoyée(s) à Supabase "
          f"({len(lignes) - ajoutees} déjà présente(s)).")


if __name__ == "__main__":
    main()

    