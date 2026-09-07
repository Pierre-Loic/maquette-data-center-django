from django.views.generic import TemplateView, ListView
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .models import LeaderboardEntry
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# Échantillons de température en mémoire
temperature_samples = []


def estimate_tokens(text):
    """Estime le nombre de tokens à partir du texte (environ 4 caractères par token)"""
    if not text:
        return 0
    return max(1, len(text) // 4)


def call_ollama(rpi, prompt, model="falcon3:1b"):
    """Appelle Ollama en mode streaming. Retourne les tokens partiels si timeout/erreur."""
    name = rpi["name"]
    url = rpi["ollama_url"]
    print(model)
    collected = []
    token_count = 0

    try:
        payload = {"prompt": prompt, "model": model, "stream": True}
        res = requests.post(url, json=payload, timeout=120, stream=True)
        res.raise_for_status()

        for line in res.iter_lines():
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
                return name, response, token_count

            # Réponse streaming token par token
            token = chunk.get("response", "")
            if token:
                collected.append(token)

            if chunk.get("done"):
                token_count = chunk.get("eval_count") or estimate_tokens("".join(collected))
                break

        response = "".join(collected) or "(aucune réponse)"
        if not token_count:
            token_count = estimate_tokens(response)
        return name, response, token_count

    except Exception as e:
        print(f"Erreur appel Ollama pour {name} ({url}): {e}")
        if collected:
            partial = "".join(collected)
            return name, f"⚠️ *(réponse partielle — interruption)*\n\n{partial}", estimate_tokens(partial)
        return name, "🔥🤯 Surchauffe !!", 0


def fetch_temperatures():
    """Récupère les températures de tous les Raspberry Pi"""
    temps = {}
    for rpi in RASPBERRIES:
        name = rpi["name"]
        url = rpi["temp_url"]
        try:
            res = requests.get(url, timeout=2)
            res.raise_for_status()
            data = res.json()
            temps[name] = data.get("temperature_c")
        except Exception as e:
            print(f"Erreur pour {name} ({url}): {e}")
            temps[name] = None
    return temps


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
    """Retourne les températures actuelles de tous les Raspberry Pi"""
    temps = fetch_temperatures()
    now = time.time()

    # Stocke l'échantillon
    temperature_samples.append((now, temps))

    # Nettoyage : garde les 10 dernières minutes max
    cutoff = now - 600
    while temperature_samples and temperature_samples[0][0] < cutoff:
        temperature_samples.pop(0)

    return JsonResponse({
        "timestamp": time.strftime("%H:%M:%S"),
        "temperatures": temps
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

        # Début de la fenêtre : juste avant l'envoi des prompts
        window_start = time.time()

        ollama_responses = {}
        token_counts = {}

        # Appels Ollama en parallèle
        with ThreadPoolExecutor(max_workers=len(RASPBERRIES)) as executor:
            futures = [
                executor.submit(call_ollama, rpi, prompt, model)
                for rpi in RASPBERRIES
            ]

            for future in as_completed(futures):
                name, response, token_count = future.result()
                ollama_responses[name] = response
                token_counts[name] = token_count

        last_response_at = time.time()
        window_end = last_response_at + 10.0  # 10s après la fin de l'inférence

        current_game["prompt"] = prompt
        current_game["predictions"] = predictions
        current_game["ollama_responses"] = ollama_responses
        current_game["token_counts"] = token_counts
        current_game["window_start"] = window_start
        current_game["window_end"] = window_end
        current_game["last_response_at"] = last_response_at
        current_game["player_name"] = player_name

        return JsonResponse({
            "status": "started",
            "countdown_seconds": 10,  # Compte à rebours fixe de 10 secondes
            "ollama_responses": ollama_responses,
            "token_counts": token_counts,
        })

    except Exception as e:
        print(f"Erreur dans api_start_game: {e}")
        return JsonResponse({
            "status": "error",
            "message": f"Exception côté serveur: {str(e)}"
        }, status=500)


@require_http_methods(["GET"])
def api_game_status(request):
    """Retourne le statut actuel du jeu"""
    window_start = current_game.get("window_start")
    window_end = current_game.get("window_end")

    if window_start is None or window_end is None:
        return JsonResponse({"status": "no_game"})

    now = time.time()

    if now < window_end:
        remaining = int(window_end - now)
        return JsonResponse({
            "status": "waiting",
            "remaining_seconds": remaining,
            "ollama_responses": current_game.get("ollama_responses"),
            "token_counts": current_game.get("token_counts"),
        })

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

    return JsonResponse({
        "status": "finished",
        "actual_temperatures": max_temps,
        "errors": errors,
        "score": score,
        "ollama_responses": ollama_responses,
        "token_counts": current_game.get("token_counts"),
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
        name, response, token_count = call_ollama(rpi, full_prompt, model)

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
