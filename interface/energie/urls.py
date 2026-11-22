from django.urls import path

from .views import IndexView, api_etat, api_lancer, api_mesures

app_name = "energie"

urlpatterns = [
    path("", IndexView.as_view(), name="index"),
    path("api/etat", api_etat, name="api_etat"),
    path("api/lancer", api_lancer, name="api_lancer"),
    path("api/mesures", api_mesures, name="api_mesures"),
]
