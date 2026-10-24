"""
Ton Wrapped de la semaine.
Lit les écoutes rangées dans historique/ par ecoutes.py, calcule les statistiques de chaque semaine
et les enregistre dans wrapped.json, que la page wrapped.html affiche.
"""

import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
DOSSIER = Path("historique")
FICHIER_SORTIE = "wrapped.json"
TOP = 5                # nombre d'artistes et de titres dans les classements
MAX_DECOUVERTES = 8


# ---------- Outils ----------

def cle_semaine(jour):
    """Une date -> '2026-S43' (même format que les fichiers de historique/)."""
    annee, semaine, _ = jour.isocalendar()
    return f"{annee}-S{semaine:02d}"


def lundi_de(cle):
    """'2026-S43' -> la date du lundi de cette semaine."""
    annee, numero = cle.split("-S")
    return date.fromisocalendar(int(annee), int(numero), 1)


def heure_de_paris(ecoute):
    """La date d'une écoute (en UTC chez Spotify) convertie à l'heure de Paris."""
    return datetime.fromisoformat(ecoute["date"].replace("Z", "+00:00")).astimezone(PARIS)


def minutes_totales(ecoutes):
    return round(sum(e["duree_ms"] for e in ecoutes) / 60000)


def variation(actuel, avant):
    """Variation en % par rapport à avant, ou None si on ne peut pas la calculer."""
    if not avant:
        return None
    return round((actuel - avant) / avant * 100)


def compter_artistes(ecoutes):
    """Nombre d'écoutes par artiste : un featuring compte pour chacun des artistes du morceau."""
    return Counter(nom for e in ecoutes for nom in e["artistes"])


def classement(compteur):
    """{nom: rang} : 1 pour le plus écouté, 2 pour le suivant..."""
    return {nom: rang for rang, (nom, _) in enumerate(compteur.most_common(), start=1)}


# ---------- Le résumé d'une semaine ----------

def resumer(cle, ecoutes, precedente, deja_entendus, maintenant, debut_collecte):
    lundi = lundi_de(cle)
    dimanche = lundi + timedelta(days=6)
    en_cours = lundi <= maintenant.date() <= dimanche

    # comparaison : la semaine précédente entière, ou jusqu'au même moment si la semaine est en cours
    comparaison = None
    if precedente is not None:
        if en_cours:
            limite = maintenant - timedelta(days=7)
            comparaison = [e for e in precedente if heure_de_paris(e) <= limite]
        else:
            comparaison = precedente

    minutes = minutes_totales(ecoutes)
    artistes = compter_artistes(ecoutes)
    morceaux = Counter(e["id"] for e in ecoutes)
    infos = {e["id"]: e for e in ecoutes}

    # pochette de chaque artiste : celle de son morceau le plus écouté de la semaine
    pochette_artiste = {}
    for id_morceau, _ in morceaux.most_common():
        for nom in infos[id_morceau]["artistes"]:
            pochette_artiste.setdefault(nom, infos[id_morceau]["pochette"])

    # classement de la semaine précédente, pour savoir qui monte et qui descend
    rangs_avant = classement(compter_artistes(precedente)) if precedente is not None else None

    top_artistes = []
    for rang, (nom, nb) in enumerate(artistes.most_common(TOP), start=1):
        if rangs_avant is None:
            mouvement = None
        elif nom not in rangs_avant:
            mouvement = "nouveau"
        else:
            mouvement = rangs_avant[nom] - rang      # positif : l'artiste monte
        top_artistes.append({"nom": nom, "ecoutes": nb, "pochette": pochette_artiste.get(nom), "mouvement": mouvement})

    top_titres = [
        {
            "titre": infos[id_morceau]["titre"],
            "artistes": ", ".join(infos[id_morceau]["artistes"]),
            "ecoutes": nb,
            "pochette": infos[id_morceau]["pochette"],
            "lien": infos[id_morceau].get("lien"),
        }
        for id_morceau, nb in morceaux.most_common(TOP)
    ]

    # découvertes : artistes jamais écoutés les semaines d'avant (seulement si on a déjà de l'historique)
    decouvertes = None
    if deja_entendus:
        decouvertes = [{"nom": nom, "ecoutes": nb} for nom, nb in artistes.most_common()
                       if nom not in deja_entendus][:MAX_DECOUVERTES]

    # rythme : minutes par jour (lundi -> dimanche) et écoutes par heure (0 h -> 23 h)
    minutes_par_jour = [0.0] * 7
    ecoutes_par_heure = [0] * 24
    for e in ecoutes:
        moment = heure_de_paris(e)
        minutes_par_jour[moment.weekday()] += e["duree_ms"] / 60000
        ecoutes_par_heure[moment.hour] += 1

    return {
        "semaine": cle,
        "numero": int(cle.split("-S")[1]),
        "du": lundi.isoformat(),
        "au": dimanche.isoformat(),
        "en_cours": en_cours,
        "debut_collecte": debut_collecte,
        "ecoutes": len(ecoutes),
        "minutes": minutes,
        "titres_differents": len(morceaux),
        "artistes_differents": len(artistes),
        "evolution": None if comparaison is None else {
            "minutes": variation(minutes, minutes_totales(comparaison)),
            "ecoutes": variation(len(ecoutes), len(comparaison)),
        },
        "top_artistes": top_artistes,
        "top_titres": top_titres,
        "decouvertes": decouvertes,
        "minutes_par_jour": [round(m) for m in minutes_par_jour],
        "ecoutes_par_heure": ecoutes_par_heure,
    }


# ---------- Programme principal ----------

def main():
    semaines = {}
    for fichier in sorted(DOSSIER.glob("*.json")):
        semaines[fichier.stem] = json.loads(fichier.read_text(encoding="utf-8"))

    maintenant = datetime.now(PARIS)
    resumes = []

    if semaines:
        premiere = min(semaines)        # la collecte a commencé en cours de route cette semaine-là
        deja_entendus = set()
        for cle in sorted(semaines):    # de la plus ancienne à la plus récente
            ecoutes = semaines[cle]
            cle_avant = cle_semaine(lundi_de(cle) - timedelta(days=7))
            # pas de comparaison avec la toute première semaine : elle est incomplète
            precedente = semaines.get(cle_avant) if cle_avant != premiere else None
            resumes.append(resumer(cle, ecoutes, precedente, deja_entendus, maintenant, cle == premiere))
            deja_entendus |= set(compter_artistes(ecoutes))

    resultat = {
        "genere_le": maintenant.isoformat(timespec="seconds"),
        "semaines": list(reversed(resumes)),     # la plus récente en premier
    }
    with open(FICHIER_SORTIE, "w", encoding="utf-8") as fichier:
        json.dump(resultat, fichier, ensure_ascii=False, indent=2)

    if not resumes:
        print("Aucune écoute dans historique/ pour l'instant.")
        return
    for s in resultat["semaines"]:
        etat = " (en cours)" if s["en_cours"] else ""
        numero_un = s["top_artistes"][0]["nom"] if s["top_artistes"] else "-"
        print(f"{s['semaine']}{etat} : {s['ecoutes']} écoutes, {s['minutes']} min, n°1 : {numero_un}")
    print(f"\nEnregistré dans {FICHIER_SORTIE}")


if __name__ == "__main__":
    main()

    