"""
Ton Wrapped de la semaine.
Lit les écoutes (historique/), la météo (meteo/) et les films choisis (films.json),
calcule les statistiques de chaque semaine et les enregistre dans wrapped.json,
que la page wrapped.html affiche.
"""

import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
DOSSIER = Path("historique")
DOSSIER_METEO = Path("meteo")
FICHIER_FILMS = Path("films.json")
FICHIER_SORTIE = "wrapped.json"
TOP = 5                          # nombre d'artistes et de titres dans les classements
MAX_DECOUVERTES = 8
HEURES_EVEILLEES = range(8, 24)  # pour la météo, on ne compte que les heures entre 8 h et minuit

NOMS_METEO = {"degage": "Ciel dégagé", "nuageux": "Nuageux", "pluie": "Pluie", "neige": "Neige"}


# ---------- Outils ----------

def cle_semaine(jour):
    """Une date -> '2026-S43' (même format que les fichiers de historique/)."""
    annee, semaine, _ = jour.isocalendar()
    return f"{annee}-S{semaine:02d}"


def lundi_de(cle):
    """'2026-S43' -> la date du lundi de cette semaine."""
    annee, numero = cle.split("-S")
    return date.fromisocalendar(int(annee), int(numero), 1)


def charger_dossier(dossier):
    """Lit tous les fichiers <semaine>.json d'un dossier -> {'2026-S43': contenu, ...}."""
    return {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in sorted(dossier.glob("*.json"))}


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


def top_titres(ecoutes, nombre):
    """Les titres les plus écoutés, avec leur pochette et leur lien Spotify."""
    morceaux = Counter(e["id"] for e in ecoutes)
    infos = {e["id"]: e for e in ecoutes}
    return [
        {
            "titre": infos[id_morceau]["titre"],
            "artistes": ", ".join(infos[id_morceau]["artistes"]),
            "ecoutes": nb,
            "pochette": infos[id_morceau].get("pochette"),
            "lien": infos[id_morceau].get("lien"),
        }
        for id_morceau, nb in morceaux.most_common(nombre)
    ]


def categorie_meteo(code):
    """Code météo international (WMO) -> 'degage', 'nuageux', 'pluie' ou 'neige'."""
    if code in (0, 1):
        return "degage"
    if code in (2, 3, 45, 48):
        return "nuageux"
    if code in (71, 73, 75, 77, 85, 86):
        return "neige"
    return "pluie"      # bruine, pluie, averses et orages


# ---------- Musique et météo ----------

def resumer_meteo(ecoutes, meteo):
    """Croise les écoutes avec la météo de Paris, heure par heure, entre 8 h et minuit."""
    if not meteo:
        return None

    heures = Counter()          # nombre d'heures de chaque type de temps
    temperatures = []
    jours_de_pluie = set()
    for cle_heure, releve in meteo.items():
        moment = datetime.strptime(cle_heure, "%Y-%m-%dT%H")
        if moment.hour not in HEURES_EVEILLEES:
            continue
        categorie = categorie_meteo(releve["code"])
        heures[categorie] += 1
        temperatures.append(releve["temperature"])
        if categorie == "pluie":
            jours_de_pluie.add(moment.date())
    if not heures:
        return None

    minutes = Counter()         # minutes écoutées par type de temps
    artistes = {categorie: Counter() for categorie in NOMS_METEO}
    for e in ecoutes:
        moment = heure_de_paris(e)
        releve = meteo.get(moment.strftime("%Y-%m-%dT%H"))
        if releve is None or moment.hour not in HEURES_EVEILLEES:
            continue
        categorie = categorie_meteo(releve["code"])
        minutes[categorie] += e["duree_ms"] / 60000
        artistes[categorie].update(e["artistes"])

    # pluie contre temps sec : minutes écoutées par heure, pour comparer à durée égale
    heures_seches = heures["degage"] + heures["nuageux"] + heures["neige"]
    minutes_seches = minutes["degage"] + minutes["nuageux"] + minutes["neige"]
    ratio = None
    if heures["pluie"] >= 3 and heures_seches and minutes_seches:
        ratio = round((minutes["pluie"] / heures["pluie"]) / (minutes_seches / heures_seches), 1)

    categories = []
    for cle, nom in NOMS_METEO.items():
        if heures[cle] == 0:
            continue
        top = artistes[cle].most_common(1)
        categories.append({
            "cle": cle,
            "nom": nom,
            "heures": heures[cle],
            "minutes": round(minutes[cle]),
            "minutes_par_heure": round(minutes[cle] / heures[cle], 1),
            "top_artiste": top[0][0] if top and top[0][1] >= 3 else None,   # au moins 3 écoutes
        })

    return {
        "temperature_moyenne": round(sum(temperatures) / len(temperatures)),
        "heures_de_pluie": heures["pluie"],
        "jours_de_pluie": len(jours_de_pluie),
        "ratio_pluie": ratio,
        "categories": categories,
    }


# ---------- Il y a un an ----------

def souvenir(cle, semaines, ecoutes_actuelles):
    """Le top de la même semaine, l'année précédente (si l'historique remonte jusque-là)."""
    annee, numero = cle.split("-S")
    cle_avant = f"{int(annee) - 1}-S{numero}"
    ecoutes = semaines.get(cle_avant)
    if not ecoutes:
        return None
    lundi = lundi_de(cle_avant)
    artistes_actuels = set(compter_artistes(ecoutes_actuelles))
    return {
        "semaine": cle_avant,
        "annee": int(annee) - 1,
        "du": lundi.isoformat(),
        "au": (lundi + timedelta(days=6)).isoformat(),
        "minutes": minutes_totales(ecoutes),
        "top_artistes": [{"nom": nom, "ecoutes": nb, "encore": nom in artistes_actuels}
                         for nom, nb in compter_artistes(ecoutes).most_common(3)],
        "top_titres": top_titres(ecoutes, 3),
    }


# ---------- Le résumé d'une semaine ----------

def resumer(cle, ecoutes, precedente, deja_entendus, maintenant, debut_collecte, semaines, meteo, film):
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
            pochette_artiste.setdefault(nom, infos[id_morceau].get("pochette"))

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
        "top_titres": top_titres(ecoutes, TOP),
        "decouvertes": decouvertes,
        "minutes_par_jour": [round(m) for m in minutes_par_jour],
        "ecoutes_par_heure": ecoutes_par_heure,
        "meteo": resumer_meteo(ecoutes, meteo),
        "il_y_a_un_an": souvenir(cle, semaines, ecoutes),
        "film": film,
    }


# ---------- Programme principal ----------

def main():
    semaines = charger_dossier(DOSSIER)
    meteo = charger_dossier(DOSSIER_METEO)
    films = json.loads(FICHIER_FILMS.read_text(encoding="utf-8")) if FICHIER_FILMS.exists() else {}

    maintenant = datetime.now(PARIS)
    resumes = []
    souvenirs_a_partir_du = None

    if semaines:
        premiere = min(semaines)        # la collecte a commencé en cours de route cette semaine-là
        annee, numero = premiere.split("-S")
        try:
            souvenirs_a_partir_du = date.fromisocalendar(int(annee) + 1, int(numero), 1).isoformat()
        except ValueError:              # semaine 53 qui n'existe pas l'année suivante
            souvenirs_a_partir_du = (lundi_de(premiere) + timedelta(weeks=52)).isoformat()

        deja_entendus = set()
        for cle in sorted(semaines):    # de la plus ancienne à la plus récente
            ecoutes = semaines[cle]
            cle_avant = cle_semaine(lundi_de(cle) - timedelta(days=7))
            # pas de comparaison avec la toute première semaine : elle est incomplète
            precedente = semaines.get(cle_avant) if cle_avant != premiere else None
            resumes.append(resumer(cle, ecoutes, precedente, deja_entendus, maintenant, cle == premiere,
                                   semaines, meteo.get(cle), films.get(cle)))
            deja_entendus |= set(compter_artistes(ecoutes))

    resultat = {
        "genere_le": maintenant.isoformat(timespec="seconds"),
        "souvenirs_a_partir_du": souvenirs_a_partir_du,
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
        film = f", film : {s['film']['titre']}" if s["film"] else ""
        print(f"{s['semaine']}{etat} : {s['ecoutes']} écoutes, {s['minutes']} min, n°1 : {numero_un}{film}")
    print(f"\nEnregistré dans {FICHIER_SORTIE}")


if __name__ == "__main__":
    main()