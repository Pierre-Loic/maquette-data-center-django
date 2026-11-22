import json

from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import moteur
from .contenu import AUTONOMIES, INFOS, MISSIONS, OUTILS, PHASES


class IndexView(TemplateView):
    template_name = "agentique/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["outils"] = OUTILS
        context["config"] = {
            "urlEtat": reverse("agentique:api_etat"),
            "urlLancer": reverse("agentique:api_lancer"),
            "urlDecider": reverse("agentique:api_decider"),
            "csrf": get_token(self.request),
            "missions": MISSIONS,
            "autonomies": AUTONOMIES,
            "outils": OUTILS,
            "phases": PHASES,
            "infos": INFOS,
        }
        return context


def _json(request):
    try:
        return json.loads(request.body)
    except ValueError:
        return None


@require_GET
def api_etat(request):
    return JsonResponse(moteur.etat())


@require_POST
def api_lancer(request):
    data = _json(request)
    try:
        run = moteur.lancer(str(data["mission"]), str(data["autonomie"]))
    except (TypeError, KeyError, ValueError):
        return JsonResponse({"erreur": "Paramètres invalides"}, status=400)
    if run is None:
        return JsonResponse({"erreur": "Une mission est déjà en cours", **moteur.etat()}, status=409)
    return JsonResponse(moteur.etat())


@require_POST
def api_decider(request):
    data = _json(request)
    try:
        run_id, ok = int(data["run"]), data["ok"]
    except (TypeError, KeyError, ValueError):
        return JsonResponse({"erreur": "Paramètres invalides"}, status=400)
    if not isinstance(ok, bool):
        return JsonResponse({"erreur": "Paramètres invalides"}, status=400)
    if not moteur.decider(run_id, ok):
        return JsonResponse({"erreur": "Aucune action en attente", **moteur.etat()}, status=409)
    return JsonResponse(moteur.etat())
