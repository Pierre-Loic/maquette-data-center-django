from django.views.generic import TemplateView, ListView
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .models import LeaderboardEntry
import requests
import time
import threading
import queue
from concurrent.futures import ThreadPoolExecutor
import json
import os

RAG_CONTEXTS_PATH = os.path.join(os.path.dirname(__file__), "rag_contexts.json")

def _load_rag_contexts():
    try:
        with open(RAG_CONTEXTS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

# Configuration des Raspberry Pi
RASPBERRIES = [
    {
        "name": "Sans refroidissement 🔳",
        "temp_url": "http://192.168.137.10:8000/metrics/temperature",
        "ollama_url": "http://192.168.137.10:8000/ollama/generate",
    },
    {
        "name": "Refroidissement passif ♨️",
        "temp_url": "http://192.168.137.11:8000/metrics/temperature",
        "ollama_url": "http://192.168.137.11:8000/ollama/generate",
    },
    {
        "name": "Refroidissement actif air 🍃",
        "temp_url": "http://192.168.137.12:8000/metrics/temperature",
        "ollama_url": "http://192.168.137.12:8000/ollama/generate",
    },
]

# État du jeu en mémoire (pour une vraie app, utiliser cache Django ou Redis)
current_game = {
    "started_at": None,
    "prompt": None,
    "predictions": None,
    "ollama_responses": None,
    "player_name": None,
    "window_start": None,
    "window_end": None,
}

# Verrou protégeant les accès concurrents à current_game (le thread de
# génération écrit les tokens au fil de l'eau pendant que les requêtes de
# statut le lisent).
_game_lock = threading.Lock()

# Compteur de parties (identifie la partie en cours pour ignorer les threads
# d'une partie abandonnée).
_game_seq = 0

# Échantillons de température en mémoire
temperature_samples = []

# Puissance électrique constante supposée pour un Raspberry Pi pendant la
# génération du texte (utilisée pour estimer le coût énergétique d'une réponse).
POWER_WATTS = 14.0


def estimate_tokens(text):
    """Estime le nombre de tokens à partir du texte (environ 4 caractères par token)"""
    if not text:
        return 0
    return max(1, len(text) // 4)


def call_ollama(rpi, prompt, model="falcon3:1b", on_progress=None):
    """Appelle Ollama en mode streaming. Retourne les tokens partiels si timeout/erreur.

    Retourne un tuple (name, response, token_count, generation_seconds) où
    generation_seconds mesure le temps écoulé entre l'envoi de la requête et la
    fin de la génération du texte pour ce Raspberry Pi.

    `on_progress`, si fourni, est appelé au fil de la génération avec
    (name, texte_partiel, nombre_de_tokens_estimé) pour permettre l'affichage
    en streaming côté navigateur.
    """
    name = rpi["name"]
    url = rpi["ollama_url"]
    print(model)
    collected = []
    token_count = 0
    started_at = time.time()

    def _emit_progress():
        if on_progress is None:
            return
        try:
            partial = "".join(collected)
            on_progress(name, partial, token_count or estimate_tokens(partial))
        except Exception:
            pass

    try:
        payload = {"prompt": prompt, "model": model, "stream": True}
        res = requests.post(url, json=payload, timeout=300, stream=True)
        res.raise_for_status()

        # chunk_size=None => une ligne est renvoyée dès qu'un chunk HTTP arrive
        # (sinon requests bufferise ~512 octets avant de céder la main, ce qui
        # casse le streaming token par token).
        for line in res.iter_lines(chunk_size=None):
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue

            # Réponse non-streaming (API retourne un seul objet JSON)
            if "response" in chunk and not isinstance(chunk.get("done"), bool):
                response = chunk.get("response", "(aucune réponse)")
                token_count = chunk.get("eval_count") or estimate_tokens(response)
                if on_progress is not None:
                    try:
                        on_progress(name, response, token_count)
                    except Exception:
                        pass
                return name, response, token_count, time.time() - started_at

            # Réponse streaming token par token
            token = chunk.get("response", "")
            if token:
                collected.append(token)
                _emit_progress()

            if chunk.get("done"):
                token_count = chunk.get("eval_count") or estimate_tokens("".join(collected))
                break

        generation_seconds = time.time() - started_at
        response = "".join(collected) or "(aucune réponse)"
        if not token_count:
            token_count = estimate_tokens(response)
        return name, response, token_count, generation_seconds

    except Exception as e:
        print(f"Erreur appel Ollama pour {name} ({url}): {e}")
        generation_seconds = time.time() - started_at
        if collected:
            partial = "".join(collected)
            return name, f"⚠️ *(réponse partielle — interruption)*\n\n{partial}", estimate_tokens(partial), generation_seconds
        return name, "🔥🤯 Surchauffe !!", 0, generation_seconds


def fetch_metrics():
    """Récupère toutes les métriques système de tous les Raspberry Pi."""
    metrics = {}
    for rpi in RASPBERRIES:
        name = rpi["name"]
        url = rpi["temp_url"]
        try:
            res = requests.get(url, timeout=2)
            res.raise_for_status()
            data = res.json()
            cpu_load = data.get("cpu_load_percent")
            cpu_freq = data.get("cpu_freq_mhz")
            metrics[name] = {
                "temperature_c":    data.get("temperature_c"),
                "ram_used_percent": data.get("ram_used_percent"),
                "cpu_load_percent": cpu_load.get("avg") if isinstance(cpu_load, dict) else cpu_load,
                "cpu_freq_mhz":     cpu_freq.get("avg") if isinstance(cpu_freq, dict) else cpu_freq,
            }
        except Exception as e:
            print(f"Erreur métriques pour {name} ({url}): {e}")
            metrics[name] = {"temperature_c": None, "ram_used_percent": None,
                             "cpu_load_percent": None, "cpu_freq_mhz": None}
    return metrics


def fetch_temperatures():
    """Extrait uniquement les températures (pour temperature_samples)."""
    return {name: m["temperature_c"] for name, m in fetch_metrics().items()}


class HomeView(TemplateView):
    template_name = "dashboard/fonctionnement.html"


class GameView(TemplateView):
    """Vue principale du jeu"""
    template_name = "dashboard/game.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['raspberries'] = [r["name"] for r in RASPBERRIES]
        context['rag_contexts'] = json.dumps(_load_rag_contexts(), ensure_ascii=False)
        return context


class LeaderboardView(ListView):
    model = LeaderboardEntry
    template_name = "dashboard/classement.html"
    context_object_name = "entries"
    paginate_by = 25

    def get_queryset(self):
        # Tri principal: points desc, puis date (comme dans Meta.ordering)
        # On peut aussi limiter les champs récupérés pour optimiser.
        return (
            LeaderboardEntry.objects
            .all()
            .only(
                "pseudo", "points",
                "predicted_temp_pi1", "predicted_temp_pi2", "predicted_temp_pi3",
                "max_temp_pi1", "max_temp_pi2", "max_temp_pi3",
                "prompt",
                "answer_pi1", "answer_pi2", "answer_pi3",
                "created_at"
            )
        )


# ==================== API Views ====================

@require_http_methods(["GET"])
def api_temperatures(request):
    """Retourne les métriques système actuelles de tous les Raspberry Pi."""
    all_metrics = fetch_metrics()
    now = time.time()

    temps = {name: m["temperature_c"] for name, m in all_metrics.items()}

    # Stocke l'échantillon de température (pour le calcul des max en fin de partie)
    temperature_samples.append((now, temps))
    cutoff = now - 600
    while temperature_samples and temperature_samples[0][0] < cutoff:
        temperature_samples.pop(0)

    return JsonResponse({
        "timestamp": time.strftime("%H:%M:%S"),
        "temperatures":    temps,
        "ram_used_percent":  {name: m["ram_used_percent"]  for name, m in all_metrics.items()},
        "cpu_load_percent":  {name: m["cpu_load_percent"]  for name, m in all_metrics.items()},
        "cpu_freq_mhz":      {name: m["cpu_freq_mhz"]      for name, m in all_metrics.items()},
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_start_game(request):
    """Lance une nouvelle partie du jeu"""
    global current_game

    try:
        data = json.loads(request.body)
        prompt = data.get("prompt", "")
        predictions = data.get("predictions", {}) or {}
        player_name = data.get("player_name", "Joueur")
        model = data.get("model", "falcon3:1b")

        rpi_names = [r["name"] for r in RASPBERRIES]

        # Début de la fenêtre : juste avant l'envoi des prompts
        window_start = time.time()

        # Identifiant de partie : permet aux threads de génération d'une partie
        # abandonnée (nouveau lancement pendant que l'ancienne tourne) de cesser
        # d'écrire dans l'état partagé.
        global _game_seq
        _game_seq += 1
        game_id = _game_seq

        # File d'événements consommée par le flux SSE (api_game_stream) : chaque
        # token généré y est poussé pour un affichage token par token.
        event_q = queue.Queue()

        # Initialise l'état partagé : la génération se fait dans un thread de fond
        # et écrit les tokens au fil de l'eau ; le flux SSE et les requêtes de
        # statut le lisent.
        with _game_lock:
            current_game.clear()
            current_game.update({
                "game_id": game_id,
                "prompt": prompt,
                "predictions": predictions,
                "player_name": player_name,
                "model": model,
                "window_start": window_start,
                "window_end": None,          # défini quand les 3 RPi ont terminé
                "last_response_at": None,
                "streaming": True,
                "saved": False,
                "ollama_responses": {name: "" for name in rpi_names},
                "token_counts": {name: 0 for name in rpi_names},
                "generation_times": {},
                "energy_costs": {},
                "done_flags": {name: False for name in rpi_names},
                "event_q": event_q,
            })

        _last_emit = {}  # name -> timestamp du dernier événement 'token'

        def _on_progress(name, partial_text, token_est):
            with _game_lock:
                if current_game.get("game_id") != game_id or not current_game.get("streaming"):
                    return
                current_game["ollama_responses"][name] = partial_text
                current_game["token_counts"][name] = token_est
            # ~20 événements/s par RPi : per-token à l'œil, sans saturer le flux
            now = time.time()
            if now - _last_emit.get(name, 0.0) < 0.05:
                return
            _last_emit[name] = now
            event_q.put({
                "type": "token",
                "name": name,
                "text": partial_text,
                "tokens": token_est,
            })

        def _run_one(rpi):
            name = rpi["name"]
            _, response, token_count, generation_seconds = call_ollama(
                rpi, prompt, model, on_progress=_on_progress
            )
            all_done = False
            with _game_lock:
                if current_game.get("game_id") != game_id:
                    return  # partie abandonnée
                current_game["ollama_responses"][name] = response
                current_game["token_counts"][name] = token_count
                current_game["generation_times"][name] = round(generation_seconds, 2)
                current_game["energy_costs"][name] = round(
                    POWER_WATTS * generation_seconds / 3600.0, 4
                )
                current_game["done_flags"][name] = True
                if all(current_game["done_flags"].values()):
                    all_done = True
                    last = time.time()
                    current_game["streaming"] = False
                    current_game["last_response_at"] = last
                    current_game["window_end"] = last + 10.0  # 10s après la fin

            event_q.put({
                "type": "rpi_done",
                "name": name,
                "text": response,
                "tokens": token_count,
                "generation_time": round(generation_seconds, 2),
                "energy_wh": round(POWER_WATTS * generation_seconds / 3600.0, 4),
            })
            if all_done:
                event_q.put({"type": "all_done"})

        def _worker():
            with ThreadPoolExecutor(max_workers=len(RASPBERRIES)) as executor:
                list(executor.map(_run_one, RASPBERRIES))

        threading.Thread(target=_worker, daemon=True).start()

        return JsonResponse({
            "status": "started",
            "streaming": True,
            "countdown_seconds": 10,  # Compte à rebours fixe de 10 secondes
            "ollama_responses": current_game["ollama_responses"],
            "token_counts": current_game["token_counts"],
        })

    except Exception as e:
        print(f"Erreur dans api_start_game: {e}")
        return JsonResponse({
            "status": "error",
            "message": f"Exception côté serveur: {str(e)}"
        }, status=500)


def _sse(obj):
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@require_http_methods(["GET"])
def api_game_stream(request):
    """Flux Server-Sent Events : pousse les tokens des 3 Raspberry Pi au fil de
    l'eau vers le navigateur (affichage token par token)."""
    with _game_lock:
        event_q = current_game.get("event_q")
        game_id = current_game.get("game_id")
        streaming = current_game.get("streaming", False)
        snapshot_responses = dict(current_game.get("ollama_responses") or {})
        snapshot_tokens = dict(current_game.get("token_counts") or {})

    def event_stream():
        # État courant d'abord (utile si le client se connecte après le début)
        yield _sse({
            "type": "snapshot",
            "responses": snapshot_responses,
            "token_counts": snapshot_tokens,
        })

        if event_q is None or not streaming:
            yield _sse({"type": "all_done"})
            return

        while True:
            try:
                item = event_q.get(timeout=15)
            except queue.Empty:
                # commentaire SSE = keepalive (empêche la coupure des proxys)
                yield ": keepalive\n\n"
                with _game_lock:
                    if current_game.get("game_id") != game_id:
                        return
                continue

            yield _sse(item)
            if item.get("type") == "all_done":
                return

    response = StreamingHttpResponse(
        event_stream(), content_type="text/event-stream"
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # désactive le buffering nginx éventuel
    return response


@require_http_methods(["GET"])
def api_game_status(request):
    """Retourne le statut actuel du jeu"""
    with _game_lock:
        window_start = current_game.get("window_start")
        window_end = current_game.get("window_end")
        streaming = current_game.get("streaming", False)
        snapshot = {
            "ollama_responses": dict(current_game.get("ollama_responses") or {}),
            "token_counts": dict(current_game.get("token_counts") or {}),
            "generation_times": dict(current_game.get("generation_times") or {}),
            "energy_costs": dict(current_game.get("energy_costs") or {}),
        }

    if window_start is None:
        return JsonResponse({"status": "no_game"})

    now = time.time()

    # Génération en cours : les tokens arrivent au fil de l'eau (streaming)
    if streaming or window_end is None:
        return JsonResponse({
            "status": "streaming",
            **snapshot,
            "power_watts": POWER_WATTS,
        })

    if now < window_end:
        remaining = int(window_end - now)
        return JsonResponse({
            "status": "waiting",
            "remaining_seconds": remaining,
            **snapshot,
            "power_watts": POWER_WATTS,
        })

    # Partie déjà finalisée (ou finalisation en cours par un autre poll) :
    # on renvoie l'état figé sans re-sauvegarder en base.
    with _game_lock:
        if current_game.get("saved") or current_game.get("finalizing"):
            frozen = {
                "status": "finished",
                "actual_temperatures": current_game.get("max_temps"),
                "errors": current_game.get("errors"),
                "score": current_game.get("score"),
                **snapshot,
                "power_watts": POWER_WATTS,
                "window_start": window_start,
                "window_end": window_end,
                "top3": current_game.get("top3"),
            }
            claimed = False
        else:
            current_game["finalizing"] = True  # réserve la finalisation
            claimed = True

    if not claimed:
        return JsonResponse(frozen)

    # Fenêtre terminée → calcul des max à partir de l'historique
    relevant_samples = [
        temps for (ts, temps) in temperature_samples
        if window_start <= ts <= window_end
    ]

    rpi_names = [r["name"] for r in RASPBERRIES]

    max_temps = {}
    for name in rpi_names:
        values = []
        for temps in relevant_samples:
            t = temps.get(name)
            if t is not None:
                values.append(t)
        max_temps[name] = max(values) if values else None

    predictions = current_game["predictions"] or {}

    errors = {}
    score = 0.0

    for name in rpi_names:
        try:
            predicted = float(predictions.get(name))
        except (TypeError, ValueError):
            predicted = None

        actual = max_temps.get(name)

        if actual is None or predicted is None:
            errors[name] = None
            continue

        err = round(abs(actual - predicted) / actual * 100, 2)
        errors[name] = err
        score += max(0.0, 10.0 - err)

    # Sauvegarder dans la base de données
    player_name = current_game.get("player_name", "Joueur")
    prompt = current_game.get("prompt", "")
    ollama_responses = current_game.get("ollama_responses", {})

    # Mapper les noms aux champs du modèle
    rpi_mapping = {
        "Refroidissement passif ♨️": (1, "pi1"),
        "Refroidissement actif air 🍃": (2, "pi2"),
        "Sans refroidissement 🔳": (3, "pi3"),
    }

    # Préparer les données pour la sauvegarde
    entry_data = {
        "pseudo": player_name,
        "points": int(score),
        "prompt": prompt,
    }

    for rpi_name in rpi_names:
        if rpi_name in rpi_mapping:
            _, field_suffix = rpi_mapping[rpi_name]

            # Prédiction
            try:
                pred_value = float(predictions.get(rpi_name))
                entry_data[f"predicted_temp_{field_suffix}"] = pred_value
            except (TypeError, ValueError):
                pass

            # Température max
            if max_temps.get(rpi_name) is not None:
                entry_data[f"max_temp_{field_suffix}"] = max_temps[rpi_name]

            # Réponse Ollama
            if ollama_responses.get(rpi_name):
                entry_data[f"answer_{field_suffix}"] = ollama_responses[rpi_name]

    # Créer l'entrée dans la base de données
    LeaderboardEntry.objects.create(**entry_data)

    # Récupérer le top 3
    top3 = LeaderboardEntry.objects.all()[:3]
    top3_data = [
        {
            "name": entry.pseudo,
            "score": entry.points
        }
        for entry in top3
    ]

    # Fige le résultat pour que les polls suivants ne re-sauvegardent pas
    with _game_lock:
        current_game["saved"] = True
        current_game["max_temps"] = max_temps
        current_game["errors"] = errors
        current_game["score"] = score
        current_game["top3"] = top3_data

    return JsonResponse({
        "status": "finished",
        "actual_temperatures": max_temps,
        "errors": errors,
        "score": score,
        "ollama_responses": ollama_responses,
        "token_counts": current_game.get("token_counts"),
        "generation_times": current_game.get("generation_times"),
        "energy_costs": current_game.get("energy_costs"),
        "power_watts": POWER_WATTS,
        "window_start": window_start,
        "window_end": window_end,
        "top3": top3_data,
    })


# ==================== Dialogue entre modèles ====================

class DialogueView(TemplateView):
    """Vue pour le dialogue entre modèles"""
    template_name = "dashboard/dialogue.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['raspberries'] = [r["name"] for r in RASPBERRIES]
        return context


@csrf_exempt
@require_http_methods(["POST"])
def api_dialogue_next(request):
    """Génère la prochaine réponse dans le dialogue"""
    try:
        data = json.loads(request.body)
        model = data.get("model", "falcon3:1b")
        model_index = data.get("model_index", 0)
        conversation_history = data.get("conversation_history", [])

        if not RASPBERRIES:
            return JsonResponse({
                "status": "error",
                "message": "Aucun Raspberry Pi configuré"
            }, status=400)

        # Sélectionner le Raspberry Pi pour ce tour
        rpi = RASPBERRIES[model_index % len(RASPBERRIES)]

        # Construire le prompt avec l'historique de conversation
        prompt_parts = []
        previous_responses = []

        for msg in conversation_history:
            if msg["model"] == "system":
                prompt_parts.append(msg['content'])
            else:
                previous_responses.append(msg['content'])

        if previous_responses:
            prompt_parts.append("\n--- DÉJÀ DIT (NE PAS RÉPÉTER) ---")
            for i, resp in enumerate(previous_responses, 1):
                prompt_parts.append(f"{i}. {resp}")
            prompt_parts.append("--- FIN ---\n")

        prompt_parts.append(f"Votre réponse (une seule phrase nouvelle) :")
        full_prompt = "\n".join(prompt_parts)

        # Appeler Ollama
        name, response, token_count, _ = call_ollama(rpi, full_prompt, model)

        return JsonResponse({
            "status": "success",
            "model": name,
            "response": response,
            "tokens": token_count,
        })

    except Exception as e:
        print(f"Erreur dans api_dialogue_next: {e}")
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


# ==================== Puissance instantanée ====================

SMART_PLUG_URL = "http://10.181.12.35/cm?cmnd=Status%208"


@require_http_methods(["GET"])
def api_power(request):
    """Récupère la puissance instantanée depuis la prise connectée"""
    try:
        # Connection: close évite le keep-alive, incompatible avec Tasmota
        res = requests.get(SMART_PLUG_URL, timeout=2, headers={"Connection": "close"})
        res.raise_for_status()
        data = res.json()
        energy = data.get("StatusSNS", {}).get("ENERGY", {})
        return JsonResponse({
            "status": "success",
            "power": energy.get("Power"),
            "voltage": energy.get("Voltage"),
            "current": energy.get("Current"),
        })
    except Exception as e:
        print(f"Erreur récupération puissance: {e}")
        return JsonResponse({
            "status": "error",
            "message": str(e)
        })
