"""
Mode réel : envoi de la question au vrai Raspberry Pi et lecture de ses métriques.

Deux façons de parler au Pi (Pi 1, 2 et 3 = les 3 Raspberry Pi de RASPBERRIES
dans dashboard/views.py) :

  1. directement à Ollama (port 11434) — méthode privilégiée :
       GET  /api/ps        -> modèles réellement chargés en RAM
       POST /api/generate  -> sans prompt : charge le modèle (durée mesurée) ;
                              avec prompt : réponse token par token (streaming)
                              et, à la fin, les durées exactes de la lecture du
                              prompt (prefill) et de la génération (decode) ;
  2. à l'API FastAPI du Pi (port 8000), si Ollama n'est pas joignable :
       POST /ollama/generate {prompt, model} -> réponse complète d'un bloc
       (le simulateur du launcher, lui, répond en streaming).

Les mesures du Pi (température, RAM, CPU) viennent de GET /metrics/temperature.
"""

import json
import queue
import re
import threading
import time
from urllib.parse import urlparse

import requests

from dashboard.views import RASPBERRIES

from . import simulation
from .contenu import MODELES, PRE_PROMPT, QUESTIONS

OLLAMA_PORT = 11434
# Durée pendant laquelle Ollama garde le modèle en RAM après usage (évite de
# longs rechargements pendant le salon)
KEEP_ALIVE = "30m"
# Au-delà, la réponse est coupée pour qu'elle reste lisible sur le schéma
MAX_TOKENS = 60
# Requête minimale qui oblige le Pi à charger le modèle (API FastAPI, sans
# chargement seul possible)
PROMPT_CHARGEMENT = "Réponds uniquement : OK."
# Attente maximale d'une réponse du Pi (chargement d'un gros modèle compris)
DELAI_LECTURE_S = 150
DUREE_MAX_S = 150
# Durées minimales d'affichage. Envoi, découpage et lecture du prompt ne
# prennent en réalité que quelques millisecondes : sans ce délai on ne les
# verrait pas. Les durées réelles sont mesurées et affichées.
AFFICHAGE_ENVOI_S = 1.2
AFFICHAGE_TOKEN_QUESTION_S = 0.3
AFFICHAGE_APRES_CHARGEMENT_S = 1.2
AFFICHAGE_LECTURE_S = 2.2
# Temps laissé pour lire la pastille du pré-prompt caché (Ministral)
AFFICHAGE_PREPROMPT_CACHE_S = 2.6
# Rythme d'affichage d'une réponse reçue en un seul bloc (s par mot)
AFFICHAGE_MOT_S = 0.12


def _rpi(pi: int) -> dict:
    return RASPBERRIES[pi - 1]


def _ollama(pi: int) -> str:
    """URL du serveur Ollama du Pi (même machine que son API de métriques)."""
    return f"http://{urlparse(_rpi(pi)['temp_url']).hostname}:{OLLAMA_PORT}"


def modeles_en_ram(pi: int):
    """Noms des modèles chargés en RAM sur le Pi ; None si Ollama est injoignable."""
    try:
        r = requests.get(_ollama(pi) + "/api/ps", timeout=1.5)
        r.raise_for_status()
        return [m.get("name") or m.get("model") for m in r.json().get("models", [])]
    except (requests.RequestException, ValueError):
        return None


# ---------------------------------------------------------------------------
# Lecture du flux de réponse dans un fil séparé (heure d'arrivée exacte)
# ---------------------------------------------------------------------------
_COUPURE = object()
_FIN = object()


def _lecteur(res, flux: queue.Queue) -> None:
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
    mots = re.findall(r"\S+", texte.strip())
    return [("" if i == 0 else " ") + m for i, m in enumerate(mots)]


class _Generation:
    """Outils communs aux deux façons de parler au Pi."""

    def __init__(self, run_id, q, pi, model):
        self.run_id, self.q, self.pi, self.model = run_id, q, pi, model
        self.question = QUESTIONS[q]["q"]
        self.prompt = f"{PRE_PROMPT}\n\nQuestion : {self.question}"
        self.ollama = MODELES[model]["ollama"]
        self.t0 = time.time()

    def ev(self, type_, **data):
        return simulation.ajouter_evenement(self.run_id, type_, **data)

    def echec(self, message):
        self.ev("error", message=message)
        simulation.terminer(self.run_id)

    def attendre(self, t):
        """Attend jusqu'à t secondes après l'envoi."""
        reste = self.t0 + t - time.time()
        if reste > 0:
            time.sleep(reste)

    def maintenant(self):
        return time.time() - self.t0

    def envoi_et_decoupage(self):
        tokens = simulation.tokeniser(self.question)
        self.attendre(AFFICHAGE_ENVOI_S)
        self.ev("received")
        cache = MODELES[self.model]["preprompt_cache"]
        self.ev("tokenized", tokens=tokens, n_prompt=simulation.tokens_du_prompt(self.q, self.model),
                n_cache=cache, fournisseur=MODELES[self.model]["fournisseur"])
        # (plus de temps pour lire la pastille du pré-prompt caché, s'il y en a un)
        self.attendre(AFFICHAGE_ENVOI_S + (len(tokens) + 3) * AFFICHAGE_TOKEN_QUESTION_S
                      + (AFFICHAGE_PREPROMPT_CACHE_S if cache else 0))

    def debut_ecriture(self, debut_lecture, premier_token):
        """Fin de la lecture du prompt (au 1er token) : affichée au moins
        AFFICHAGE_LECTURE_S, avec sa durée réelle."""
        self.attendre(debut_lecture - self.t0 + AFFICHAGE_LECTURE_S)
        duree = None if premier_token is None else int((premier_token - debut_lecture) * 1000)
        self.ev("prefill_end", n_prompt=simulation.tokens_du_prompt(self.q, self.model), duree_ms=duree)
        self.ev("generation_start")

    def fin(self, stats, tronque=False, index=0):
        if tronque:
            self.ev("token", text=" […]", index=index)
        simulation.marquer_charge(self.pi, self.model)
        self.ev("generation_end", stats=stats)
        self.ev("done")
        simulation.terminer(self.run_id)


def generer(run_id: int, q: int, pi: int, model: str, deja_charge: bool) -> None:
    """Envoie la question au Pi choisi et transforme sa réponse en événements."""
    g = _Generation(run_id, q, pi, model)
    en_ram = modeles_en_ram(pi)
    if en_ram is None:
        return _generer_fastapi(g, deja_charge)
    _generer_ollama(g, g.ollama in en_ram)


# ---------------------------------------------------------------------------
# 1. Directement avec Ollama : streaming et durées exactes
# ---------------------------------------------------------------------------
def _generer_ollama(g: _Generation, deja_charge: bool) -> None:
    url = _ollama(g.pi) + "/api/generate"
    g.envoi_et_decoupage()

    # Chargement du modèle en RAM (requête sans prompt), sauf s'il y est déjà
    if deja_charge:
        g.ev("load_skipped")
        simulation.marquer_charge(g.pi, g.model)
    else:
        g.ev("load_start")
        debut = time.time()
        try:
            r = requests.post(url, json={"model": g.ollama, "keep_alive": KEEP_ALIVE, "stream": False},
                              timeout=(4, DELAI_LECTURE_S))
            r.raise_for_status()
            charge = r.json()
        except (requests.RequestException, ValueError) as e:
            print(f"[vie du prompt] échec du chargement sur le Pi {g.pi} : {e}")
            return g.echec(f"Le modèle {g.model} n’a pas pu être chargé sur le Pi {g.pi}.")
        if charge.get("error"):
            print(f"[vie du prompt] erreur Ollama sur le Pi {g.pi} : {charge['error']}")
            return g.echec(f"Le modèle {g.model} n’est pas disponible sur le Pi {g.pi}.")
        simulation.marquer_charge(g.pi, g.model)
        g.ev("loaded", duree_ms=int((time.time() - debut) * 1000))
    g.attendre(g.maintenant() + AFFICHAGE_APRES_CHARGEMENT_S)

    # Lecture du prompt (prefill) puis génération des tokens (decode)
    g.ev("prefill_start", n_prompt=simulation.tokens_du_prompt(g.q, g.model))
    debut_lecture = time.time()
    try:
        res = requests.post(url, json={"model": g.ollama, "prompt": g.prompt, "stream": True,
                                       "keep_alive": KEEP_ALIVE, "options": {"num_predict": MAX_TOKENS}},
                            stream=True, timeout=(4, DELAI_LECTURE_S))
        res.raise_for_status()
    except requests.RequestException as e:
        print(f"[vie du prompt] Pi {g.pi} injoignable : {e}")
        return g.echec(f"Le Raspberry Pi {g.pi} ne répond pas.")

    flux = queue.Queue()
    threading.Thread(target=_lecteur, args=(res, flux), daemon=True).start()
    n, fin = 0, None
    try:
        for chunk, arrivee in _lire_en_parallele(res, flux):
            if chunk is _COUPURE:
                print(f"[vie du prompt] coupure pendant la réponse du Pi {g.pi} : {arrivee}")
                if n == 0:
                    return g.echec(f"Le Raspberry Pi {g.pi} n’a pas répondu (surchauffe ?).")
                break
            if chunk.get("error"):
                print(f"[vie du prompt] erreur Ollama sur le Pi {g.pi} : {chunk['error']}")
                return g.echec(f"Le modèle {g.model} n’a pas pu répondre sur le Pi {g.pi}.")
            texte = chunk.get("response", "")
            if texte:
                if n == 0:
                    g.debut_ecriture(debut_lecture, arrivee)
                # tr = heure réelle d'arrivée (ms depuis l'envoi)
                if not g.ev("token", text=texte, index=n, tr=int((arrivee - g.t0) * 1000)):
                    return  # génération remplacée entre-temps
                n += 1
            if chunk.get("done"):
                fin = chunk
                break
            if time.time() - g.t0 > DUREE_MAX_S:
                break
    finally:
        res.close()

    if n == 0:
        return g.echec("Aucune réponse du modèle.")
    stats = None
    if fin:
        # Durées exactes mesurées par Ollama (en nanosecondes)
        stats = {
            "prompt_tokens": fin.get("prompt_eval_count"),
            "prompt_cached": fin.get("prompt_eval_cached_count", 0),
            "prompt_ms": round(fin.get("prompt_eval_duration", 0) / 1e6),
            "gen_tokens": fin.get("eval_count"),
            "gen_ms": round(fin.get("eval_duration", 0) / 1e6),
        }
    tronque = fin is None or fin.get("done_reason") == "length"
    g.fin(stats, tronque, n)


# ---------------------------------------------------------------------------
# 2. Secours : API FastAPI du Pi (réponse complète d'un bloc)
# ---------------------------------------------------------------------------
def _generer_fastapi(g: _Generation, deja_charge: bool) -> None:
    url = _rpi(g.pi)["ollama_url"]
    if not metriques(g.pi).get("ok"):
        print(f"[vie du prompt] Pi {g.pi} injoignable")
        return g.echec(f"Le Raspberry Pi {g.pi} ne répond pas.")
    g.envoi_et_decoupage()

    if deja_charge:
        g.ev("load_skipped")
    else:
        # Une requête très courte oblige le Pi à charger le modèle en RAM
        g.ev("load_start")
        debut = time.time()
        try:
            r = requests.post(url, json={"prompt": PROMPT_CHARGEMENT, "model": g.ollama}, timeout=(4, DELAI_LECTURE_S))
            r.raise_for_status()
            r.close()
        except requests.RequestException as e:
            print(f"[vie du prompt] échec du chargement sur le Pi {g.pi} : {e}")
            return g.echec(f"Le modèle {g.model} n’a pas pu être chargé sur le Pi {g.pi}.")
        simulation.marquer_charge(g.pi, g.model)
        g.ev("loaded", duree_ms=int((time.time() - debut) * 1000))
    g.attendre(g.maintenant() + AFFICHAGE_APRES_CHARGEMENT_S)

    g.ev("prefill_start", n_prompt=simulation.tokens_du_prompt(g.q, g.model))
    debut_lecture = time.time()
    try:
        res = requests.post(url, json={"prompt": g.prompt, "model": g.ollama}, stream=True, timeout=(4, DELAI_LECTURE_S))
        res.raise_for_status()
    except requests.RequestException as e:
        print(f"[vie du prompt] Pi {g.pi} injoignable : {e}")
        return g.echec(f"Le Raspberry Pi {g.pi} ne répond pas.")

    flux = queue.Queue()
    threading.Thread(target=_lecteur, args=(res, flux), daemon=True).start()
    n, tronque, en_bloc = 0, False, None
    try:
        for chunk, arrivee in _lire_en_parallele(res, flux):
            if chunk is _COUPURE:
                print(f"[vie du prompt] coupure pendant la réponse du Pi {g.pi} : {arrivee}")
                if n == 0:
                    return g.echec(f"Le Raspberry Pi {g.pi} n’a pas répondu (surchauffe ?).")
                tronque = True
                break
            if chunk.get("error"):
                print(f"[vie du prompt] erreur Ollama sur le Pi {g.pi} : {chunk['error']}")
                return g.echec(f"Le modèle {g.model} n’a pas pu répondre sur le Pi {g.pi}.")
            texte = chunk.get("response", "")
            if "done" not in chunk:
                en_bloc = texte  # réponse complète d'un seul bloc
                break
            if texte:  # flux token par token (simulateur du launcher)
                if n == 0:
                    g.debut_ecriture(debut_lecture, arrivee)
                if not g.ev("token", text=texte, index=n, tr=int((arrivee - g.t0) * 1000)):
                    return
                n += 1
            if chunk["done"]:
                break
            if n >= MAX_TOKENS or time.time() - g.t0 > DUREE_MAX_S:
                tronque = True
                break
    finally:
        res.close()

    if en_bloc is not None:
        # Le Pi a tout calculé d'un coup : lecture et écriture ne sont pas séparables
        calcul_ms = int((time.time() - debut_lecture) * 1000)
        mots = _mots(en_bloc)
        if not mots:
            return g.echec("Aucune réponse du modèle.")
        g.debut_ecriture(debut_lecture, None)
        for i, mot in enumerate(mots[:MAX_TOKENS]):
            g.attendre(g.maintenant() + AFFICHAGE_MOT_S)
            if not g.ev("token", text=mot, index=i):
                return
        return g.fin({"total_ms": calcul_ms, "gen_tokens": max(1, len(en_bloc) // 4)},
                     len(mots) > MAX_TOKENS, MAX_TOKENS)

    if n == 0:
        return g.echec("Aucune réponse du modèle.")
    g.fin(None, tronque, n)


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
