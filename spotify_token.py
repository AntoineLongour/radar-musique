"""
À lancer une seule fois : autorise ton app Spotify à lire tes artistes
et affiche ta clé longue durée (le « refresh token »).
Rien n'est enregistré dans un fichier : tu copieras la clé dans les secrets GitHub.
"""

import secrets
import urllib.parse

import requests

REDIRECT_URI = "http://127.0.0.1:8888/callback"   # doit être exactement celle déclarée dans ton app Spotify
SCOPES = "user-top-read user-follow-read"         # lecture seule : tes artistes les plus écoutés et ceux que tu suis

client_id = input("Colle ton Client ID : ").strip()
client_secret = input("Colle ton Client secret : ").strip()

# un code aléatoire pour vérifier que la réponse vient bien de ta demande
etat = secrets.token_urlsafe(16)

lien = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
    "client_id": client_id,
    "response_type": "code",
    "redirect_uri": REDIRECT_URI,
    "scope": SCOPES,
    "state": etat,
})

print("\n1. Ouvre ce lien (Ctrl + clic), connecte-toi et clique sur « Accepter » :\n")
print(lien)
print("\n2. Ton navigateur va afficher « Ce site est inaccessible » : c'est normal.")
print("   Copie l'adresse complète dans la barre d'adresse (elle commence par http://127.0.0.1)")
print("   et colle-la ci-dessous.\n")
adresse = input("Adresse : ").strip()

params = urllib.parse.parse_qs(urllib.parse.urlparse(adresse).query)
if "error" in params:
    raise SystemExit(f"Spotify a refusé l'autorisation : {params['error'][0]}")
if params.get("state", [""])[0] != etat:
    raise SystemExit("L'adresse collée ne correspond pas à ce lien. Relance le script et recommence.")
if "code" not in params:
    raise SystemExit("Pas de code dans l'adresse collée. Vérifie que tu as copié l'adresse en entier.")

# on échange le code contre les clés
reponse = requests.post(
    "https://accounts.spotify.com/api/token",
    data={"grant_type": "authorization_code", "code": params["code"][0], "redirect_uri": REDIRECT_URI},
    auth=(client_id, client_secret),
    timeout=10,
)
if reponse.status_code != 200:
    raise SystemExit(f"Échec de l'échange avec Spotify ({reponse.status_code}) : {reponse.text}")
cles = reponse.json()

# petit test : tes 5 artistes les plus écoutés ces dernières semaines
test = requests.get(
    "https://api.spotify.com/v1/me/top/artists",
    headers={"Authorization": f"Bearer {cles['access_token']}"},
    params={"time_range": "short_term", "limit": 5},
    timeout=10,
)
if test.status_code == 200:
    noms = [artiste["name"] for artiste in test.json().get("items", [])]
    print("\nÇa marche ! Tes artistes du moment :", ", ".join(noms) or "(pas encore assez d'écoutes)")
else:
    print(f"\nLa clé est créée, mais le test a échoué ({test.status_code}) : {test.text}")

print("\nTa clé longue durée (refresh token), à garder secrète :\n")
print(cles["refresh_token"])