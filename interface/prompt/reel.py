"""
Mode réel : envoi de la question au vrai Raspberry Pi et lecture de ses métriques.

Utilise les mêmes API que le reste de la plateforme (voir RASPBERRIES dans
dashboard/views.py) :
  - POST /ollama/generate     -> réponse d'Ollama en streaming (une ligne JSON par token)
  - GET  /metrics/temperature -> température, RAM, charge et fréquence du CPU

Pi 1, 2 et 3 correspondent dans l'ordre aux 3 Raspberry Pi de RASPBERRIES.
"""

import json
import queue
import threading
import time

import requests

from dashboard.views import RASPBERRIES

from . import simulation
from .contenu import MODELES, PRE_PROMPT, QUESTIONS

# Au-delà, la réponse est coupée pour qu'elle reste lisible sur le schéma
MAX_TOKENS = 120
# Attente maximale du premier token (chargement d'un gros modèle sur un Pi)
DELAI_LECTURE_S = 120
# Durée maximale d'une génération
DUREE_MAX_S = 140
# Durées minimales d'affichage des phases « Envoi » et « Arrivée » : sur le réseau
# local elles ne prennent que quelques millisecondes et seraient invisibles.
# La requête part immédiatement ; seul l'affichage de ces deux phases est
# étalé. Les tokens et les mesures restent ceux du Pi, en temps réel.
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


def generer(run_id: int, q: int, pi: int, model: str, deja_charge: bool) -> None:
    """Envoie la question au Pi choisi et transforme sa réponse en événements."""
    question = QUESTIONS[q]["q"]
    payload = {
        "prompt": f"{PRE_PROMPT}\n\nQuestion : {question}",
        "model": MODELES[model]["ollama"],
        "stream": True,
    }

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

    try:
        res = requests.post(_rpi(pi)["ollama_url"], json=payload, stream=True, timeout=(4, DELAI_LECTURE_S))
        res.raise_for_status()
    except requests.RequestException as e:
        print(f"[vie du prompt] Pi {pi} injoignable : {e}")
        echec(f"Le Raspberry Pi {pi} ne répond pas.")
        return

    # La réponse est lue dès maintenant dans un fil séparé (heures d'arrivée
    # exactes), pendant que l'affichage des premières phases suit son rythme.
    flux = queue.Queue()
    threading.Thread(target=_lecteur, args=(res, flux), daemon=True).start()

    # La requête est arrivée sur le Pi
    tokens_question = simulation.tokeniser(question)
    attendre(AFFICHAGE_ENVOI_S)
    ev("received")
    ev("tokenized", tokens=tokens_question)
    attendre(AFFICHAGE_ENVOI_S + (len(tokens_question) + 1) * AFFICHAGE_TOKEN_QUESTION_S)
    # En attendant le premier token, le Pi charge le modèle (s'il n'est pas déjà
    # en RAM) puis lit le prompt (prefill)
    if deja_charge:
        ev("load_skipped")
        ev("generation_start")
    else:
        ev("load_start")

    n, tronque = 0, False
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
            if texte:
                if n == 0:
                    if not deja_charge:
                        ev("loaded")
                        ev("generation_start")
                    simulation.marquer_charge(pi, model)
                # tr = heure réelle d'arrivée du token (ms depuis l'envoi), pour des
                # mesures « 1er token » et « débit » exactes même si l'affichage est décalé
                if not ev("token", text=texte, index=n, tr=int((arrivee - t0) * 1000)):
                    return  # génération remplacée entre-temps
                n += 1
            if chunk.get("done"):
                break
            if n >= MAX_TOKENS or time.time() - t0 > DUREE_MAX_S:
                tronque = True
                break
    finally:
        res.close()

    if n == 0:
        echec("Aucune réponse du modèle.")
        return
    if tronque:
        ev("token", text=" […]", index=n)
    simulation.marquer_charge(pi, model)
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
