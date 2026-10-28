"""
Petit module pour parler à Supabase depuis les scripts GitHub.

Il utilise la clé SECRÈTE, rangée dans les secrets GitHub (SUPABASE_URL et SUPABASE_SECRET_KEY).
Cette clé passe outre les règles d'accès : elle ne doit servir que dans les scripts GitHub,
jamais dans le site ni dans l'appli.
"""

import os
from urllib.parse import urlsplit

import requests

TAILLE_PAQUET = 500   # nombre de lignes envoyées par requête


def _adresse():
    """Adresse du projet, réduite à « https://….supabase.co » même si un /rest/v1/ traîne derrière."""
    brute = os.environ.get("SUPABASE_URL", "").strip()
    morceaux = urlsplit(brute)
    if not morceaux.scheme or not morceaux.netloc:
        raise SystemExit("Il manque le secret GitHub SUPABASE_URL (ou il est mal écrit).")
    return f"{morceaux.scheme}://{morceaux.netloc}"


def _entetes(prefer=None):
    cle = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    if not cle:
        raise SystemExit("Il manque le secret GitHub SUPABASE_SECRET_KEY.")
    entetes = {"apikey": cle, "Content-Type": "application/json"}   # les nouvelles clés passent dans « apikey »
    if prefer:
        entetes["Prefer"] = prefer
    return entetes


def appeler(methode, table, params=None, donnees=None, prefer=None):
    """Appelle l'API de Supabase sur une table et renvoie la réponse (liste de lignes)."""
    reponse = requests.request(
        methode,
        f"{_adresse()}/rest/v1/{table}",
        params=params,
        json=donnees,
        headers=_entetes(prefer),
        timeout=60,
    )
    if reponse.status_code >= 400:
        raise RuntimeError(f"Supabase a répondu {reponse.status_code} sur {table} : {reponse.text[:300]}")
    return reponse.json() if reponse.content else []


def id_du_joueur(pseudo):
    """L'identifiant du compte qui porte ce pseudo (majuscules ignorées)."""
    lignes = appeler("GET", "profils", params={"select": "id,pseudo", "pseudo": f"ilike.{pseudo}"})
    lignes = [l for l in lignes if l["pseudo"].lower() == pseudo.lower()]
    if not lignes:
        raise SystemExit(f"Aucun compte « {pseudo} » dans Supabase : crée-le sur la page connexion.html.")
    return lignes[0]["id"]


def lire_tout(table, params):
    """
    Lit toutes les lignes qui correspondent, par pages (Supabase en renvoie au plus 1 000 à la fois).
    params : un dictionnaire, ou une liste de paires pour filtrer deux fois la même colonne.
    """
    params = list(params.items()) if isinstance(params, dict) else list(params)
    lignes = []
    while True:
        page = appeler("GET", table, params=params + [("limit", 1000), ("offset", len(lignes))])
        if not page:
            return lignes
        lignes += page


def appeler_fonction(nom, arguments):
    """Lance une fonction SQL de Supabase (créée dans le SQL Editor) et renvoie son résultat."""
    return appeler("POST", f"rpc/{nom}", donnees=arguments)


def enregistrer(table, lignes, colonnes_uniques, paquet=100):
    """Ajoute les lignes, ou remplace celles qui existent déjà (même valeur dans colonnes_uniques)."""
    for debut in range(0, len(lignes), paquet):
        appeler(
            "POST", table,
            params={"on_conflict": colonnes_uniques},
            donnees=lignes[debut:debut + paquet],
            prefer="resolution=merge-duplicates,return=minimal",
        )


def ajouter_nouvelles(table, lignes, colonnes_uniques):
    """
    Ajoute les lignes, en ignorant celles qui existent déjà (même valeur dans colonnes_uniques).
    Renvoie le nombre de lignes vraiment ajoutées.
    """
    ajoutees = 0
    for debut in range(0, len(lignes), TAILLE_PAQUET):
        paquet = lignes[debut:debut + TAILLE_PAQUET]
        reponse = appeler(
            "POST", table,
            params={"on_conflict": colonnes_uniques, "select": "id"},
            donnees=paquet,
            prefer="resolution=ignore-duplicates,return=representation",
        )
        ajoutees += len(reponse)   # Supabase ne renvoie que les lignes réellement ajoutées
    return ajoutees