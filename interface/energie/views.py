import json

from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from . import moteur
from .contenu import CALCULS, LONGUEURS, MODELES, QUESTIONS


class IndexView(TemplateView):
    template_name = "energie/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["config"] = {
            "urlEtat": reverse("energie:api_etat"),
            "urlLancer": reverse("energie:api_lancer"),
            "urlMesures": reverse("energie:api_mesures"),
            "csrf": get_token(self.request),
            "questions": QUESTIONS,
            "modeles": MODELES,
            "longueurs": LONGUEURS,
            "pis": moteur.noms_pis(),
            "calculs": CALCULS,
        }
        return context


@require_GET
def api_etat(request):
    return JsonResponse(moteur.etat())


@require_GET
def api_mesures(request):
    return JsonResponse(moteur.mesures())


@require_POST
def api_lancer(request):
    try:
        data = json.loads(request.body)
        q, model, longueur = int(data["q"]), str(data["model"]), str(data["longueur"])
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"erreur": "Paramètres invalides"}, status=400)
    if not (0 <= q < len(QUESTIONS)) or model not in MODELES or longueur not in LONGUEURS:
        return JsonResponse({"erreur": "Paramètres invalides"}, status=400)
    if moteur.lancer(q, model, longueur) is None:
        return JsonResponse({"erreur": "Une génération est déjà en cours", **moteur.etat()}, status=409)
    return JsonResponse(moteur.etat())
