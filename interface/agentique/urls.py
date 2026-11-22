from django.urls import path

from .views import IndexView, api_decider, api_etat, api_lancer

app_name = "agentique"

urlpatterns = [
    path("", IndexView.as_view(), name="index"),
    path("api/etat", api_etat, name="api_etat"),
    path("api/lancer", api_lancer, name="api_lancer"),
    path("api/decider", api_decider, name="api_decider"),
]
