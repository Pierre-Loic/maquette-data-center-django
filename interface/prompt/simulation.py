"""
Déroulé d'une génération et état partagé entre les écrans.

L'écran de commande demande une génération (lancer) ; le serveur produit une
liste d'événements datés (t = ms depuis l'envoi) que le schéma rejoue en
interrogeant régulièrement l'état.

Deux modes (voir VIE_PROMPT_SIMULATION dans datacenter/settings.py) :
  - SIMULÉ (launcher en mode démo) : tout le déroulé est calculé d'avance par
    construire_evenements(), avec des durées fictives ;
  - RÉEL (maquette connectée) : la question est envoyée au vrai Raspberry Pi
    choisi (voir reel.py) et les événements sont ajoutés au fil de la réponse.
"""

import re
import threading
import time

from django.conf import settings

from .contenu import MODELES, PIS, QUESTIONS

# Ollama garde un modèle en RAM 5 min après sa dernière utilisation (keep_alive
# par défaut) : au-delà, on considère qu'il faudra le recharger.
GARDE_EN_RAM_MS = 4.5 * 60 * 1000
# Garde-fou : une génération réelle est considérée terminée au bout de ce délai
DUREE_MAX_REEL_MS = 150_000

_verrou = threading.Lock()


def _etat_initial() -> dict:
    return {
        "seq": 0,
        "run": None,
        # modèle actuellement chargé en RAM sur chaque Pi (None = vide)
        "charges": {pi: None for pi in PIS},
        # date de dernière utilisation de ce modèle sur chaque Pi (mode réel)
        "utilise_le": {pi: 0 for pi in PIS},
        # dernière sélection faite sur l'écran de commande (aperçu sur le schéma)
        "selection": {"q": 0, "pi": next(iter(PIS)), "model": next(iter(MODELES))},
    }


_etat = _etat_initial()

_TOKEN_RE = re.compile(r"[^\W_][\w'’-]*|[^\s\w]")


def mode_simulation() -> bool:
    return settings.VIE_PROMPT_SIMULATION


def maintenant_ms() -> int:
    return int(time.time() * 1000)


def tokeniser(texte: str) -> list[str]:
    """Découpage simplifié de la question en tokens (14 au maximum)."""
    return _TOKEN_RE.findall(texte)[:14]


def construire_evenements(q: int, pi: int, model: str, deja_charge: bool) -> list[dict]:
    """Mode simulé : liste chronologique des événements, avec t = ms depuis l'envoi."""
    question, mod = QUESTIONS[q], MODELES[model]
    tk = tokeniser(question["q"])
    ev = []

    def at(t, type_, **data):
        ev.append({"t": int(t), "type": type_, **data})

    T = 0
    at(T, "sent", pi=pi, model=model, prompt=question["q"])
    T += 2600
    at(T, "received")
    T += 400
    at(T, "tokenized", tokens=tk)
    T += len(tk) * 300 + 600
    if deja_charge:
        at(T, "load_skipped")
        T += 500
    else:
        at(T, "load_start")
        for k in range(1, 21):
            at(T + k * mod["load"] / 20, "load_progress", pct=k * 5)
        T += mod["load"] + 150
        at(T, "loaded")
        T += 400
    at(T, "generation_start")
    T += 1500
    for k, tok in enumerate(question["a"]):
        at(T, "token", text=tok, index=k)
        T += mod["tok"] + (k % 3) * 110
    T += 200
    at(T, "generation_end")
    T += 1100
    at(T, "done")
    return ev


def _en_cours(run, now) -> bool:
    if run is None:
        return False
    if run["duree"] is not None:
        return now < run["debut"] + run["duree"]
    return now - run["debut"] < DUREE_MAX_REEL_MS


def etat() -> dict:
    with _verrou:
        now = maintenant_ms()
        run = _etat["run"]
        return {
            "serveur": now,
            # copie : un fil d'exécution peut ajouter des événements pendant l'envoi de la réponse
            "run": {**run, "evenements": list(run["evenements"])} if run else None,
            "en_cours": _en_cours(run, now),
            "charges": dict(_etat["charges"]),
            "selection": dict(_etat["selection"]),
        }


def choisir(q: int, pi: int, model: str) -> None:
    with _verrou:
        _etat["selection"] = {"q": q, "pi": pi, "model": model}


def lancer(q: int, pi: int, model: str):
    """Démarre une génération ; renvoie None si une génération est déjà en cours."""
    simule = mode_simulation()
    with _verrou:
        now = maintenant_ms()
        if _en_cours(_etat["run"], now):
            return None
        deja_charge = _etat["charges"][pi] == model and (
            simule or now - _etat["utilise_le"][pi] < GARDE_EN_RAM_MS
        )
        _etat["seq"] += 1
        _etat["selection"] = {"q": q, "pi": pi, "model": model}
        run = {"id": _etat["seq"], "q": q, "pi": pi, "model": model, "debut": now, "mode": "simulation" if simule else "reel"}
        if simule:
            evenements = construire_evenements(q, pi, model, deja_charge)
            run.update(duree=evenements[-1]["t"], evenements=evenements)
            _etat["charges"][pi] = model
        else:
            run.update(duree=None, evenements=[
                {"t": 0, "type": "sent", "pi": pi, "model": model, "prompt": QUESTIONS[q]["q"]}
            ])
        _etat["run"] = run

    if not simule:
        from . import reel
        threading.Thread(target=reel.generer, args=(run["id"], q, pi, model, deja_charge), daemon=True).start()
    return run


# ---- mode réel : appelé par reel.py au fil de la réponse du Pi ----

def ajouter_evenement(run_id: int, type_: str, **data) -> bool:
    """Ajoute un événement à la génération en cours ; False si elle a été remplacée."""
    with _verrou:
        run = _etat["run"]
        if run is None or run["id"] != run_id or run["duree"] is not None:
            return False
        run["evenements"].append({"t": maintenant_ms() - run["debut"], "type": type_, **data})
        return True


def marquer_charge(pi: int, model: str) -> None:
    with _verrou:
        _etat["charges"][pi] = model
        _etat["utilise_le"][pi] = maintenant_ms()


def terminer(run_id: int) -> None:
    with _verrou:
        run = _etat["run"]
        if run is not None and run["id"] == run_id and run["duree"] is None:
            run["duree"] = maintenant_ms() - run["debut"]


def reinitialiser() -> None:
    """Remet l'état à zéro (utilisé par les tests)."""
    with _verrou:
        _etat.clear()
        _etat.update(_etat_initial())
