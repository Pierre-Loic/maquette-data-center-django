"""
Mode réel : envoi de la question au vrai Raspberry Pi et lecture de ses métriques.

Utilise les mêmes API que le reste de la plateforme (voir RASPBERRIES dans
dashboard/views.py) :
  - POST /ollama/generate     -> réponse complète d'Ollama {prompt, model} -> {response}
                                 (le simulateur du launcher, lui, répond en streaming)
  - GET  /metrics/temperature -> température, RAM, charge et fréquence du CPU

Pi 1, 2 et 3 correspondent dans l'ordre aux 3 Raspberry Pi de RASPBERRIES.
"""

import json
import queue
import re
import threading
import time

import requests

from dashboard.views import RASPBERRIES

from . import simulation
from .contenu import MODELES, PRE_PROMPT, QUESTIONS

# Au-delà, la réponse est coupée pour qu'elle reste lisible sur le schéma
MAX_TOKENS = 60
# Requête minimale qui oblige le Pi à charger le modèle en RAM
PROMPT_CHARGEMENT = "Réponds uniquement : OK."
# Rythme d'affichage d'une réponse reçue en un seul bloc (s par mot)
AFFICHAGE_MOT_S = 0.12
# Attente maximale du premier token (chargement d'un gros modèle sur un Pi)
DELAI_LECTURE_S = 120
# Durée maximale d'une génération
DUREE_MAX_S = 140
# Durées minimales d'affichage des phases « Envoi » et « Arrivée » : sur le réseau
# local elles ne prennent que quelques millisecondes et seraient invisibles.
# Les durées de chargement et de calcul, elles, sont mesurées sur le Pi.
AFFICHAGE_ENVOI_S = 1.2
AFFICHAGE_TOKEN_QUESTION_S = 0.3


def _rpi(pi: int) -> dict:
    return RASPBERRIES[pi - 1]


_COUPURE = object()
_FIN = object()


def _lecteur(res, flux: queue.Queue) -> None:
    """Lit le flux du Pi et note l'heure d'arrivée de chaque ligne."""
    try:
        for line in res.iter_lines(chunk_size=None):
            if line:
                flux.put((line, time.time()))
        flux.put((_FIN, time.time()))
    except Exception as e:  # coupure réseau, surchauffe du Pi, fermeture par nous…
        flux.put((_COUPURE, e))


def _lire_en_parallele(res, flux: queue.Queue):
    """Itère sur (chunk JSON, heure d'arrivée) ; (_COUPURE, erreur) en cas de coupure."""
    while True:
        try:
            line, info = flux.get(timeout=DELAI_LECTURE_S)
        except queue.Empty:
            yield _COUPURE, "délai dépassé"
            return
        if line is _FIN:
            return
        if line is _COUPURE:
            yield _COUPURE, info
            return
        try:
            yield json.loads(line), info
        except ValueError:
            continue


def _mots(texte: str) -> list[str]:
    """Découpe une réponse en mots (espaces conservés) pour l'afficher mot à mot."""
    mots = re.findall(r"\S+\s*", texte.strip())
    return [("" if i == 0 else " ") + m.rstrip() for i, m in enumerate(mots)]


def generer(run_id: int, q: int, pi: int, model: str, deja_charge: bool) -> None:
    """Envoie la question au Pi choisi et transforme sa réponse en événements.

    Les Pi de la maquette renvoient la réponse complète d'un seul bloc (pas de
    streaming ni de détail des durées). Pour distinguer réellement les étapes :
      1. Chargement : si le modèle n'est pas déjà en RAM, une première requête
         très courte oblige le Pi à le charger ; sa durée est mesurée ;
      2. Calcul : la vraie question ; le CPU calcule toute la réponse ;
      3. Affichage : la réponse reçue est affichée mot à mot.
    Si le Pi renvoie un flux token par token (simulateur), il est affiché en direct.
    """
    question = QUESTIONS[q]["q"]
    rpi = _rpi(pi)
    ollama = MODELES[model]["ollama"]

    def ev(type_, **data):
        return simulation.ajouter_evenement(run_id, type_, **data)

    def echec(message):
        ev("error", message=message)
        simulation.terminer(run_id)

    t0 = time.time()

    def attendre(t):
        reste = t0 + t - time.time()
        if reste > 0:
            time.sleep(reste)

    # Le Pi est-il joignable ? (lecture rapide de ses mesures)
    if not metriques(pi).get("ok"):
        print(f"[vie du prompt] Pi {pi} injoignable")
        echec(f"Le Raspberry Pi {pi} ne répond pas.")
        return

    # Envoi et arrivée : quelques millisecondes en réalité, étalées pour être visibles
    tokens_question = simulation.tokeniser(question)
    attendre(AFFICHAGE_ENVOI_S)
    ev("received")
    ev("tokenized", tokens=tokens_question)
    attendre(AFFICHAGE_ENVOI_S + (len(tokens_question) + 1) * AFFICHAGE_TOKEN_QUESTION_S)

    # 1. Chargement du modèle en RAM (requête très courte), sauf s'il y est déjà
    if deja_charge:
        ev("load_skipped")
    else:
        ev("load_start")
        debut = time.time()
        try:
            res = requests.post(rpi["ollama_url"], json={"prompt": PROMPT_CHARGEMENT, "model": ollama},
                                timeout=(4, DELAI_LECTURE_S))
            res.raise_for_status()
            res.close()
        except requests.RequestException as e:
            print(f"[vie du prompt] échec du chargement sur le Pi {pi} : {e}")
            echec(f"Le modèle {model} n’a pas pu être chargé sur le Pi {pi}.")
            return
        simulation.marquer_charge(pi, model)
        ev("loaded", duree_ms=int((time.time() - debut) * 1000))

    # 2. Calcul de la réponse par le CPU
    ev("generation_start")
    debut_calcul = time.time()
    try:
        res = requests.post(rpi["ollama_url"], json={"prompt": f"{PRE_PROMPT}\n\nQuestion : {question}", "model": ollama},
                            stream=True, timeout=(4, DELAI_LECTURE_S))
        res.raise_for_status()
    except requests.RequestException as e:
        print(f"[vie du prompt] Pi {pi} injoignable : {e}")
        echec(f"Le Raspberry Pi {pi} ne répond pas.")
        return

    flux = queue.Queue()
    threading.Thread(target=_lecteur, args=(res, flux), daemon=True).start()
    n, tronque, en_bloc = 0, False, None
    try:
        for chunk, arrivee in _lire_en_parallele(res, flux):
            if chunk is _COUPURE:
                print(f"[vie du prompt] coupure pendant la réponse du Pi {pi} : {arrivee}")
                if n == 0:
                    echec(f"Le Raspberry Pi {pi} n’a pas répondu (surchauffe ?).")
                    return
                tronque = True
                break
            if chunk.get("error"):
                print(f"[vie du prompt] erreur Ollama sur le Pi {pi} : {chunk['error']}")
                echec(f"Le modèle {model} n’a pas pu répondre sur le Pi {pi}.")
                return
            texte = chunk.get("response", "")
            if "done" not in chunk:
                # Réponse complète en un seul bloc (API des Pi de la maquette)
                en_bloc = texte
                break
            if texte:
                # Flux token par token : tr = heure réelle d'arrivée (ms depuis l'envoi)
                if not ev("token", text=texte, index=n, tr=int((arrivee - t0) * 1000)):
                    return  # génération remplacée entre-temps
                n += 1
            if chunk["done"]:
                break
            if n >= MAX_TOKENS or time.time() - t0 > DUREE_MAX_S:
                tronque = True
                break
    finally:
        res.close()
    simulation.marquer_charge(pi, model)

    if en_bloc is not None:
        calcul_ms = int((time.time() - debut_calcul) * 1000)
        mots = _mots(en_bloc)
        if not mots:
            echec("Aucune réponse du modèle.")
            return
        # Le calcul est terminé : la réponse est ensuite affichée mot à mot
        ev("generation_end", tokens=max(1, len(en_bloc) // 4), calcul_ms=calcul_ms)
        for i, mot in enumerate(mots[:MAX_TOKENS]):
            attendre(time.time() - t0 + AFFICHAGE_MOT_S)
            if not ev("token", text=mot, index=i):
                return
        if len(mots) > MAX_TOKENS:
            ev("token", text=" […]", index=MAX_TOKENS)
        ev("done")
        simulation.terminer(run_id)
        return

    if n == 0:
        echec("Aucune réponse du modèle.")
        return
    if tronque:
        ev("token", text=" […]", index=n)
    ev("generation_end")
    ev("done")
    simulation.terminer(run_id)


def metriques(pi: int) -> dict:
    """Mesures instantanées du Pi (None si indisponibles)."""
    try:
        res = requests.get(_rpi(pi)["temp_url"], timeout=1.5)
        res.raise_for_status()
        data = res.json()
    except (requests.RequestException, ValueError):
        return {"ok": False}

    def moyenne(v):
        return v.get("avg") if isinstance(v, dict) else v

    return {
        "ok": True,
        "temperature_c": data.get("temperature_c"),
        "ram_used_percent": data.get("ram_used_percent"),
        "cpu_load_percent": moyenne(data.get("cpu_load_percent")),
        "cpu_freq_mhz": moyenne(data.get("cpu_freq_mhz")),
    }
