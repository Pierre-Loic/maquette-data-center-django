"""
Exécution des missions de l'agent et état partagé avec la page.

Le scénario (scenarios.py) est déroulé côté serveur : chaque étape devient un
événement daté (t = ms depuis le lancement) que la page rejoue. Quand l'agent
doit faire valider une action, le déroulé s'arrête jusqu'à la décision de la
personne (ou continue tout seul si l'agent est autonome).
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from prompt.reel import metriques

from .contenu import AUTONOMIES, MISSIONS
from .scenarios import SCENARIOS

# Rythme d'affichage de la réponse finale (ms par mot)
MS_PAR_MOT = 170
_verrou = threading.Lock()
_etat = {"seq": 0, "run": None}


def maintenant_ms() -> int:
    return int(time.time() * 1000)


def lire_temperatures() -> dict:
    """Températures réelles des 3 Raspberry Pi (simulateur en mode démo)."""
    with ThreadPoolExecutor(max_workers=3) as ex:
        res = list(ex.map(metriques, (1, 2, 3)))
    return {pi: (m.get("temperature_c") if m.get("ok") else None) for pi, m in zip((1, 2, 3), res)}


def _avancer(run: dict, decision=None) -> None:
    """Déroule le scénario jusqu'à la fin ou jusqu'à la prochaine validation."""
    gen = run["_gen"]
    t = max(run["_curseur"], maintenant_ms() - run["debut"])
    envoi = decision
    while True:
        try:
            etape = gen.send(envoi)
        except StopIteration:
            run["evenements"].append({"t": t, "type": "done", "phase": "repondre"})
            run["duree"] = t
            return
        envoi = None
        d = etape.pop("d", 0)

        if etape["type"] == "validation":
            if run["autonomie"] == "autonome":
                run["evenements"].append({**etape, "t": t, "type": "auto"})
                t += 900
                envoi = True
                continue
            run["evenements"].append({"t": t, "type": "validation", **{k: v for k, v in etape.items() if k != "type"}})
            run["attente"] = {"outil": etape["outil"], "action": etape["action"]}
            run["_curseur"] = t + d
            return

        if etape["type"] == "answer":
            mots = etape["text"].split(" ")
            run["evenements"].append({"t": t, "type": "answer_start", "phase": "repondre"})
            t += 400
            for i, mot in enumerate(mots):
                run["evenements"].append({"t": t, "type": "token", "phase": "repondre",
                                          "text": ("" if i == 0 else " ") + mot})
                t += MS_PAR_MOT
            t += 600
            continue

        run["evenements"].append({"t": t, **etape})
        t += d


def _copie(run):
    if run is None:
        return None
    return {k: (list(v) if k == "evenements" else v) for k, v in run.items() if not k.startswith("_")}


def _en_cours(run, now) -> bool:
    """Génération en train de se dérouler (hors attente de validation)."""
    if run is None or run["attente"] is not None:
        return False
    return run["duree"] is None or now < run["debut"] + run["duree"]


def etat() -> dict:
    with _verrou:
        run = _etat["run"]
        return {
            "serveur": maintenant_ms(),
            "run": _copie(run),
            "en_cours": _en_cours(run, maintenant_ms()),
            "attente": dict(run["attente"]) if run and run["attente"] else None,
        }


def lancer(mission: str, autonomie: str):
    """Lance une mission ; None si une autre est en train de se dérouler.
    Une mission en attente de validation peut être remplacée (visiteur parti)."""
    if mission not in SCENARIOS or autonomie not in AUTONOMIES:
        raise ValueError("mission ou autonomie inconnue")
    with _verrou:
        if _en_cours(_etat["run"], maintenant_ms()):
            return None
    # Mesures lues en dehors du verrou (jusqu'à ~1,5 s si un Pi ne répond pas)
    gen = SCENARIOS[mission](lire_temperatures()) if mission == "serveurs" else SCENARIOS[mission]()
    with _verrou:
        if _en_cours(_etat["run"], maintenant_ms()):
            return None
        _etat["seq"] += 1
        objectif = next(m["objectif"] for m in MISSIONS if m["cle"] == mission)
        run = {
            "id": _etat["seq"], "mission": mission, "autonomie": autonomie,
            "debut": maintenant_ms(), "duree": None, "attente": None,
            "evenements": [{"t": 0, "type": "sent", "phase": "comprendre", "text": objectif}],
            "_gen": gen, "_curseur": 1200,
        }
        _avancer(run)
        _etat["run"] = run
        return _copie(run)


def decider(run_id: int, ok: bool) -> bool:
    """Décision de la personne sur l'action en attente ; False si rien n'attend."""
    with _verrou:
        run = _etat["run"]
        if run is None or run["id"] != run_id or run["attente"] is None:
            return False
        t = max(run["_curseur"], maintenant_ms() - run["debut"])
        run["evenements"].append({"t": t, "type": "decision", "phase": "agir", "ok": ok})
        run["_curseur"] = t + 900
        run["attente"] = None
        _avancer(run, ok)
        return True


def oublier() -> None:
    """Retour à l'accueil : oublie la dernière mission si elle est terminée ou
    si elle attend une validation (le visiteur est parti)."""
    with _verrou:
        if not _en_cours(_etat["run"], maintenant_ms()):
            _etat["run"] = None


def reinitialiser() -> None:
    with _verrou:
        _etat.update(seq=0, run=None)
