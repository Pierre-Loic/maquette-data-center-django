import json

from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import reel, simulation
from .contenu import INFOS, MODELES, NARRATION, PHASES, PIS, QUESTIONS, RAM_BASE


def _config(request) -> dict:
    return {
        "urlEtat": reverse("prompt:api_etat"),
        "urlLancer": reverse("prompt:api_lancer"),
        "urlSelection": reverse("prompt:api_selection"),
        "urlMetriques": reverse("prompt:api_metriques"),
        # "simulation" : déroulé et mesures simulés ; "reel" : vrais Raspberry Pi
        "mode": "simulation" if simulation.mode_simulation() else "reel",
        "csrf": get_token(request),
        "questions": QUESTIONS,
        "modeles": MODELES,
        "pis": PIS,
        "ramBase": RAM_BASE,
        "phases": PHASES,
        "infos": INFOS,
        "narration": NARRATION,
    }


class VieDuPromptView(TemplateView):
    """Page principale (un seul écran) : schéma en haut, paramètres en bas."""
    template_name = "prompt/vie_prompt.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["config"] = _config(self.request)
        return context


class CommandeView(TemplateView):
    """Option deux écrans — écran du bas : choix de la question, du Pi et du modèle."""
    template_name = "prompt/commande.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["config"] = _config(self.request)
        return context


class ObservationView(TemplateView):
    """Option deux écrans — écran du haut : schéma animé des étapes de la génération."""
    template_name = "prompt/observation.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["config"] = _config(self.request)
        return context


def _parametres(request):
    """Lit et valide {q, pi, model} ; renvoie None si invalide."""
    try:
        data = json.loads(request.body)
        q, pi, model = int(data["q"]), int(data["pi"]), str(data["model"])
    except (ValueError, KeyError, TypeError):
        return None
    if not (0 <= q < len(QUESTIONS)) or pi not in PIS or model not in MODELES:
        return None
    return q, pi, model


@require_GET
def api_etat(request):
    return JsonResponse(simulation.etat())


@require_POST
def api_selection(request):
    p = _parametres(request)
    if p is None:
        return JsonResponse({"erreur": "Paramètres invalides"}, status=400)
    simulation.choisir(*p)
    return JsonResponse(simulation.etat())


@require_POST
def api_lancer(request):
    p = _parametres(request)
    if p is None:
        return JsonResponse({"erreur": "Paramètres invalides"}, status=400)
    if simulation.lancer(*p) is None:
        return JsonResponse({"erreur": "Une génération est déjà en cours", **simulation.etat()}, status=409)
    return JsonResponse(simulation.etat())


@require_GET
def api_metriques(request):
    """Mesures en direct du Pi demandé (mode réel)."""
    try:
        pi = int(request.GET.get("pi", ""))
    except ValueError:
        pi = None
    if pi not in PIS:
        return JsonResponse({"erreur": "Pi inconnu"}, status=400)
    if simulation.mode_simulation():
        return JsonResponse({"ok": False, "simulation": True})
    return JsonResponse(reel.metriques(pi))
