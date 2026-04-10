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

# Raspberry Pi configuration
RASPBERRIES = [
    {
        "name": "Passive cooling ♨️",
        "temp_url": "http://192.168.137.10:8000/metrics/temperature",
        "ollama_url": "http://192.168.137.10:8000/ollama/generate",
    },
    {
        "name": "Active air cooling 🍃",
        "temp_url": "http://192.168.137.11:8000/metrics/temperature",
        "ollama_url": "http://192.168.137.11:8000/ollama/generate",
    },
    {
         "name": "Active water cooling 💧",
         "temp_url": "http://192.168.137.12:8000/metrics/temperature",
         "ollama_url": "http://192.168.137.12:8000/ollama/generate",
    },
]

# In-memory game state (for a real app, use Django cache or Redis)
current_game = {
    "started_at": None,
    "prompt": None,
    "predictions": None,
    "ollama_responses": None,
    "player_name": None,
    "window_start": None,
    "window_end": None,
}

# In-memory temperature samples
temperature_samples = []


def estimate_tokens(text):
    """Estimate token count from text (roughly 4 characters per token)"""
    if not text:
        return 0
    return max(1, len(text) // 4)


def call_ollama(rpi, prompt, model="gemma3:270m"):
    """Call Ollama on a given Raspberry Pi. Returns (name, response, token_count)"""
    name = rpi["name"]
    url = rpi["ollama_url"]
    print(model)
    try:
        payload = {"prompt": prompt, "model": model}
        res = requests.post(url, json=payload, timeout=120)
        res.raise_for_status()
        resp_json = res.json()
        response = resp_json.get("response", "(no response)")
        # Use eval_count if available, otherwise estimate from response
        token_count = resp_json.get("eval_count") or estimate_tokens(response)
        return name, response, token_count
    except Exception as e:
        print(f"Ollama call error for {name} ({url}): {e}")
        return name, f"🔥🤯 Overheating!!", 0


def fetch_temperatures():
    """Fetch temperatures from all Raspberry Pis"""
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
            print(f"Error for {name} ({url}): {e}")
            temps[name] = None
    return temps


class HomeView(TemplateView):
    template_name = "dashboard/fonctionnement.html"


class GameView(TemplateView):
    """Main game view"""
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
    """Return current temperatures from all Raspberry Pis"""
    temps = fetch_temperatures()
    now = time.time()

    # Store sample
    temperature_samples.append((now, temps))

    # Cleanup: keep last 10 minutes max
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
    """Start a new game round"""
    global current_game

    try:
        data = json.loads(request.body)
        prompt = data.get("prompt", "")
        predictions = data.get("predictions", {}) or {}
        player_name = data.get("player_name", "Player")
        model = data.get("model", "gemma3:270m")

        # Window start: just before sending prompts
        window_start = time.time()

        ollama_responses = {}
        token_counts = {}

        # Parallel Ollama calls
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
        window_end = last_response_at + 10.0  # 10s after inference ends

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
            "countdown_seconds": 10,  # Fixed 10-second countdown
            "ollama_responses": ollama_responses,
            "token_counts": token_counts,
        })

    except Exception as e:
        print(f"Error in api_start_game: {e}")
        return JsonResponse({
            "status": "error",
            "message": f"Server exception: {str(e)}"
        }, status=500)


@require_http_methods(["GET"])
def api_game_status(request):
    """Return current game status"""
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

    # Window ended → compute max values from history
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

    # Save to database
    player_name = current_game.get("player_name", "Player")
    prompt = current_game.get("prompt", "")
    ollama_responses = current_game.get("ollama_responses", {})

    # Map names to model fields
    rpi_mapping = {
        "Passive cooling ♨️": (1, "pi1"),
        "Active air cooling 🍃": (2, "pi2"),
        "Active water cooling 💧": (3, "pi3"),
    }

    # Prepare data for saving
    entry_data = {
        "pseudo": player_name,
        "points": int(score),
        "prompt": prompt,
    }

    for rpi_name in rpi_names:
        if rpi_name in rpi_mapping:
            _, field_suffix = rpi_mapping[rpi_name]

            # Prediction
            try:
                pred_value = float(predictions.get(rpi_name))
                entry_data[f"predicted_temp_{field_suffix}"] = pred_value
            except (TypeError, ValueError):
                pass

            # Max temperature
            if max_temps.get(rpi_name) is not None:
                entry_data[f"max_temp_{field_suffix}"] = max_temps[rpi_name]

            # Ollama response
            if ollama_responses.get(rpi_name):
                entry_data[f"answer_{field_suffix}"] = ollama_responses[rpi_name]

    # Create database entry
    LeaderboardEntry.objects.create(**entry_data)

    # Retrieve top 3
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
    """View for the model dialogue"""
    template_name = "dashboard/dialogue.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['raspberries'] = [r["name"] for r in RASPBERRIES]
        return context


@csrf_exempt
@require_http_methods(["POST"])
def api_dialogue_next(request):
    """Generate the next response in the dialogue"""
    try:
        data = json.loads(request.body)
        model = data.get("model", "gemma3:270m")
        model_index = data.get("model_index", 0)
        conversation_history = data.get("conversation_history", [])

        if not RASPBERRIES:
            return JsonResponse({
                "status": "error",
                "message": "No Raspberry Pi configured"
            }, status=400)

        # Select the Raspberry Pi for this turn
        rpi = RASPBERRIES[model_index % len(RASPBERRIES)]

        # Build prompt with conversation history
        prompt_parts = []
        previous_responses = []

        for msg in conversation_history:
            if msg["model"] == "system":
                prompt_parts.append(msg['content'])
            else:
                previous_responses.append(msg['content'])

        if previous_responses:
            prompt_parts.append("\n--- ALREADY SAID (DO NOT REPEAT) ---")
            for i, resp in enumerate(previous_responses, 1):
                prompt_parts.append(f"{i}. {resp}")
            prompt_parts.append("--- END ---\n")

        prompt_parts.append(f"Your response (one new sentence only):")
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
        print(f"Error in api_dialogue_next: {e}")
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


# ==================== Instantaneous power ====================

SMART_PLUG_URL = "http://10.23.206.35/cm?cmnd=Status%208"


@require_http_methods(["GET"])
def api_power(request):
    """Fetch instantaneous power from the smart plug"""
    try:
        res = requests.get(SMART_PLUG_URL, timeout=2)
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
        print(f"Error fetching power: {e}")
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)
