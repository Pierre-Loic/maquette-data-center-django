from django.urls import path

from .views import CommandeView, ObservationView, VieDuPromptView, api_etat, api_lancer, api_metriques, api_selection

app_name = "prompt"

urlpatterns = [
    # Un seul écran : schéma en haut, paramètres en bas
    path("", VieDuPromptView.as_view(), name="index"),
    # Option deux écrans : paramètres (écran du bas) et schéma (écran du haut)
    path("commande/", CommandeView.as_view(), name="commande"),
    path("ecran/", ObservationView.as_view(), name="ecran"),
    path("api/etat", api_etat, name="api_etat"),
    path("api/lancer", api_lancer, name="api_lancer"),
    path("api/selection", api_selection, name="api_selection"),
    path("api/metriques", api_metriques, name="api_metriques"),
]
