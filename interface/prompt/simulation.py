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


def _en_arriere_plan(fonction, *args) -> None:
    """Lance la génération réelle sans bloquer la requête (remplacé dans les tests)."""
    threading.Thread(target=fonction, args=args, daemon=True).start()


def mode_simulation() -> bool:
    return settings.VIE_PROMPT_SIMULATION


def maintenant_ms() -> int:
    return int(time.time() * 1000)


def tokeniser(texte: str) -> list[str]:
    """Découpage simplifié de la question en tokens (14 au maximum)."""
    return _TOKEN_RE.findall(texte)[:14]


def tokens_du_prompt(q: int, model: str) -> int:
    """Nombre approximatif de tokens lus : pré-prompt + question, plus le
    pré-prompt caché que certains modèles ajoutent eux-mêmes."""
    from .contenu import PRE_PROMPT
    return max(1, len(f"{PRE_PROMPT} {QUESTIONS[q]['q']}") // 4) + MODELES[model]["preprompt_cache"]


def tokens_du_preprompt() -> int:
    from .contenu import PRE_PROMPT
    return max(1, len(PRE_PROMPT) // 4)


# Durée minimale d'affichage de la lecture du prompt : en vrai elle ne prend
# que quelques dizaines de millisecondes et serait invisible (sa durée réelle
# est affichée dans le bandeau).
AFFICHAGE_LECTURE_MS = 2200


def construire_evenements(q: int, pi: int, model: str, deja_charge: bool) -> list[dict]:
    """Mode simulé : liste chronologique des événements, avec t = ms depuis l'envoi."""
    question, mod = QUESTIONS[q], MODELES[model]
    tk = tokeniser(question["q"])
    n_prompt = tokens_du_prompt(q, model)
    ev = []

    def at(t, type_, **data):
        ev.append({"t": int(t), "type": type_, **data})

    T = 0
    at(T, "sent", pi=pi, model=model, prompt=question["q"])
    T += 2600
    at(T, "received")
    T += 400
    at(T, "tokenized", tokens=tk, n_prompt=n_prompt, n_cache=mod["preprompt_cache"], fournisseur=mod["fournisseur"])
    T += len(tk) * 300 + (3500 if mod["preprompt_cache"] else 900)
    if deja_charge:
        at(T, "load_skipped")
        T += 1500
    else:
        at(T, "load_start")
        for k in range(1, 21):
            at(T + k * mod["load"] / 20, "load_progress", pct=k * 5)
        T += mod["load"] + 150
        at(T, "loaded", duree_ms=mod["load"])
        T += 1200
    # Modèle déjà en RAM : le début du prompt (pré-prompts) est encore en cache
    en_cache = mod["preprompt_cache"] + tokens_du_preprompt() if deja_charge else 0
    lecture_ms = int(1000 * (n_prompt - en_cache) / mod["lecture"])
    at(T, "prefill_start", n_prompt=n_prompt)
    T += max(AFFICHAGE_LECTURE_MS, lecture_ms)
    at(T, "prefill_end", n_prompt=n_prompt, duree_ms=lecture_ms)
    at(T, "generation_start")
    T += 300
    debut_gen = T
    pas = 1000 / mod["ecriture"]
    for k, tok in enumerate(question["a"]):
        at(T, "token", text=tok, index=k)
        T += pas * (0.85 + 0.15 * (k % 3))   # léger irrégularité, comme sur un vrai Pi
    gen_ms = int(T - debut_gen)
    at(T, "generation_end", stats={"prompt_tokens": n_prompt, "prompt_cached": en_cache, "prompt_ms": lecture_ms,
                                    "gen_tokens": len(question["a"]), "gen_ms": gen_ms})
    T += 1500
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
        _en_arriere_plan(reel.generer, run["id"], q, pi, model, deja_charge)
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


def oublier() -> None:
    """Retour à l'accueil : oublie la dernière génération si elle est terminée
    (les modèles chargés dans la RAM des Pi, eux, restent connus)."""
    with _verrou:
        if not _en_cours(_etat["run"], maintenant_ms()):
            _etat["run"] = None
        _etat["selection"] = _etat_initial()["selection"]


def reinitialiser() -> None:
    """Remet l'état à zéro (utilisé par les tests)."""
    with _verrou:
        _etat.clear()
        _etat.update(_etat_initial())
