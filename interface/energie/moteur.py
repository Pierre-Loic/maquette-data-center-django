"""
Envoi d'un prompt aux 3 Raspberry Pi et suivi de la génération.

Le même prompt est envoyé en parallèle aux 3 Pi de la maquette (vrais Pi, ou
simulateur du launcher en mode démo : voir RASPBERRIES dans dashboard/views.py).
Pour chaque Pi on mesure la durée de génération et le nombre de tokens ; la
page en déduit l'énergie consommée et la compare à ChatGPT.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from dashboard.views import RASPBERRIES, call_ollama
from prompt.reel import metriques

from .contenu import LONGUEURS, MESURE_APRES_S, MODELES, QUESTIONS

_verrou = threading.Lock()
_etat = {"seq": 0, "run": None}


def _en_arriere_plan(fonction, *args) -> None:
    """Lance la génération sans bloquer la requête (remplacé dans les tests)."""
    threading.Thread(target=fonction, args=args, daemon=True).start()


def noms_pis() -> list[str]:
    return [r["name"] for r in RASPBERRIES]


def construire_prompt(q: int, longueur: str) -> str:
    return f"{QUESTIONS[q]['prompt']} {LONGUEURS[longueur]['consigne']}"


def _en_cours(run) -> bool:
    return run is not None and not all(p["fini"] for p in run["pis"].values())


def _en_mesure(run, now) -> bool:
    """Génération en cours ou dans les secondes qui suivent (température)."""
    if run is None:
        return False
    if _en_cours(run):
        return True
    return run["fin"] is not None and now < run["fin"] + MESURE_APRES_S


def etat() -> dict:
    with _verrou:
        run = _etat["run"]
        copie = None
        if run is not None:
            copie = {**run, "pis": {n: dict(p) for n, p in run["pis"].items()}}
        return {
            "run": copie,
            "en_cours": _en_cours(run),
            "en_mesure": _en_mesure(run, time.time()),
        }


def lancer(q: int, model: str, longueur: str):
    """Démarre une génération sur les 3 Pi ; None si une génération est en cours."""
    with _verrou:
        if _en_cours(_etat["run"]):
            return None
        _etat["seq"] += 1
        run = {
            "id": _etat["seq"],
            "q": q,
            "model": model,
            "longueur": longueur,
            "prompt": construire_prompt(q, longueur),
            "debut": time.time(),
            "fin": None,
            "pis": {
                nom: {"texte": "", "tokens": 0, "secondes": None, "fini": False, "temp_max": None}
                for nom in noms_pis()
            },
        }
        _etat["run"] = run

    _en_arriere_plan(_generer, run["id"], run["prompt"], MODELES[model]["ollama"])
    return run


def _generer(run_id: int, prompt: str, modele_ollama: str) -> None:
    def progression(nom, texte, tokens):
        with _verrou:
            run = _etat["run"]
            if run is None or run["id"] != run_id:
                return
            run["pis"][nom].update(texte=texte, tokens=tokens)

    def un_pi(rpi):
        nom, texte, tokens, secondes = call_ollama(rpi, prompt, modele_ollama, on_progress=progression)
        with _verrou:
            run = _etat["run"]
            if run is None or run["id"] != run_id:
                return
            run["pis"][nom].update(texte=texte, tokens=tokens, secondes=round(secondes, 2), fini=True)
            if all(p["fini"] for p in run["pis"].values()):
                run["fin"] = time.time()

    with ThreadPoolExecutor(max_workers=len(RASPBERRIES)) as ex:
        list(ex.map(un_pi, RASPBERRIES))


def mesures() -> dict:
    """Métriques des 3 Pi (lues en parallèle) ; met à jour les températures max
    de la génération en cours."""
    with ThreadPoolExecutor(max_workers=len(RASPBERRIES)) as ex:
        resultats = list(ex.map(metriques, range(1, len(RASPBERRIES) + 1)))
    par_nom = dict(zip(noms_pis(), resultats))

    with _verrou:
        run = _etat["run"]
        if _en_mesure(run, time.time()):
            for nom, m in par_nom.items():
                t = m.get("temperature_c") if m.get("ok") else None
                if t is not None:
                    p = run["pis"][nom]
                    p["temp_max"] = t if p["temp_max"] is None else max(p["temp_max"], t)
    return {"heure": time.strftime("%H:%M:%S"), "pis": par_nom}


def reinitialiser() -> None:
    """Remet l'état à zéro (utilisé par les tests)."""
    with _verrou:
        _etat.update(seq=0, run=None)
