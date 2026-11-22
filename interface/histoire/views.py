import json

from django.db.models import Q
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from .models import DUREE_MAX_MS, THEMES, FriseScore

TAILLE_CLASSEMENT = 10
PSEUDO_DEFAUT = "Anonyme"


class IndexView(TemplateView):
    template_name = "histoire/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["frise_config"] = {
            "urlClassement": reverse("histoire:api_classement"),
            "urlScore": reverse("histoire:api_score"),
            "csrf": get_token(self.request),
            "classements": _classements(),
        }
        return context


def _entree(score: FriseScore) -> dict:
    return {
        "id": score.id,
        "pseudo": score.pseudo,
        "theme": score.theme,
        "ms": score.temps_ms,
        "erreurs": score.erreurs,
    }


def _classements() -> dict:
    """Top N de chaque thématique (record = premier élément)."""
    return {
        th: [_entree(s) for s in FriseScore.objects.filter(theme=th)[:TAILLE_CLASSEMENT]]
        for th in THEMES
    }


def _rang(score: FriseScore) -> int:
    """Position du score dans sa thématique (1 = meilleur)."""
    meilleurs = FriseScore.objects.filter(theme=score.theme).filter(
        Q(temps_ms__lt=score.temps_ms)
        | Q(temps_ms=score.temps_ms, erreurs__lt=score.erreurs)
        | Q(temps_ms=score.temps_ms, erreurs=score.erreurs, created_at__lt=score.created_at)
    )
    return meilleurs.count() + 1


@require_GET
def api_classement(request):
    return JsonResponse({"classements": _classements()})


@require_POST
def api_score(request):
    """Enregistre une partie gagnée et renvoie le classement mis à jour."""
    try:
        data = json.loads(request.body)
        theme = str(data["theme"])
        temps_ms = int(data["ms"])
        erreurs = int(data.get("erreurs", 0))
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"erreur": "Données invalides"}, status=400)

    if theme not in THEMES or not (0 < temps_ms <= DUREE_MAX_MS) or not (0 <= erreurs <= 100):
        return JsonResponse({"erreur": "Données invalides"}, status=400)

    pseudo = " ".join(str(data.get("pseudo", "")).split())[:20] or PSEUDO_DEFAUT

    score = FriseScore.objects.create(pseudo=pseudo, theme=theme, temps_ms=temps_ms, erreurs=erreurs)
    return JsonResponse({
        "score": _entree(score),
        "rang": _rang(score),
        "total": FriseScore.objects.filter(theme=theme).count(),
        "classements": _classements(),
    })
