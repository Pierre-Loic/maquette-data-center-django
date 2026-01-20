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

# Configuration des Raspberry Pi
RASPBERRIES = [
    {
        "name": "Refroidissement passif ♨️",
        "temp_url": "http://192.168.137.10:8000/metrics/temperature",
        "ollama_url": "http://192.168.137.10:8000/ollama/generate",
    },
    {
        "name": "Refroidissement actif air 💨",
        "temp_url": "http://192.168.137.11:8000/metrics/temperature",
        "ollama_url": "http://192.168.137.11:8000/ollama/generate",
    },
    # {
    #     "name": "Refroidissement actif eau 💧",
    #     "temp_url": "http://192.168.137.12:8000/metrics/temperature",
    #     "ollama_url": "http://192.168.137.12:8000/ollama/generate",
    # },
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


def call_ollama(rpi, prompt):
    """Appelle Ollama sur un Raspberry Pi donné"""
    name = rpi["name"]
    url = rpi["ollama_url"]
    try:
        payload = {"prompt": prompt}
        res = requests.post(url, json=payload, timeout=120)
        res.raise_for_status()
        resp_json = res.json()
        return name, resp_json.get("response", "(aucune réponse)")
    except Exception as e:
        print(f"Erreur appel Ollama pour {name} ({url}): {e}")
        return name, f"Erreur en appelant Ollama sur {name}."


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

        # Début de la fenêtre : juste avant l'envoi des prompts
        window_start = time.time()

        ollama_responses = {}

        # Appels Ollama en parallèle
        with ThreadPoolExecutor(max_workers=len(RASPBERRIES)) as executor:
            futures = [
                executor.submit(call_ollama, rpi, prompt)
                for rpi in RASPBERRIES
            ]

            for future in as_completed(futures):
                name, response = future.result()
                ollama_responses[name] = response

        last_response_at = time.time()
        window_end = last_response_at + 10.0  # 10s après la fin de l'inférence

        current_game["prompt"] = prompt
        current_game["predictions"] = predictions
        current_game["ollama_responses"] = ollama_responses
        current_game["window_start"] = window_start
        current_game["window_end"] = window_end
        current_game["last_response_at"] = last_response_at
        current_game["player_name"] = player_name

        return JsonResponse({
            "status": "started",
            "countdown_seconds": 10,  # Compte à rebours fixe de 10 secondes
            "ollama_responses": ollama_responses,
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
        "Refroidissement actif air 💨": (2, "pi2"),
        "Refroidissement actif eau 💧": (3, "pi3"),
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
        "window_start": window_start,
        "window_end": window_end,
        "top3": top3_data,
    })
