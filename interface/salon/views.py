from django.views.generic import TemplateView

# Les 4 activités du stand. Garder les textes très courts :
# sur un salon, les visiteurs ne lisent pas, ils cliquent.
ACTIVITES = [
    {
        "slug": "histoire",
        "titre": "L'IA à travers le temps",
        "accroche": "De 1950 à aujourd'hui",
        "url": "histoire:index",
        "icone": "salon/icones/histoire.svg",
    },
    {
        "slug": "energie",
        "titre": "L'IA consomme combien ?",
        "accroche": "L'énergie d'une question",
        "url": "energie:index",
        "icone": "salon/icones/energie.svg",
    },
    {
        "slug": "prompt",
        "titre": "La vie d'un prompt",
        "accroche": "Du clavier à la réponse",
        "url": "prompt:index",
        "icone": "salon/icones/prompt.svg",
    },
    {
        "slug": "agentique",
        "titre": "L'IA qui agit",
        "accroche": "Les agents IA",
        "url": "agentique:index",
        "icone": "salon/icones/agentique.svg",
    },
]


class AccueilView(TemplateView):
    template_name = "salon/accueil.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["activites"] = ACTIVITES
        return context
