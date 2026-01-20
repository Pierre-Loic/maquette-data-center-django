from django.urls import path
from .views import (
    LeaderboardView,
    HomeView,
    GameView,
    api_temperatures,
    api_start_game,
    api_game_status
)

urlpatterns = [
    path("", HomeView.as_view(), name="fonctionnement"),
    path("jeu/", GameView.as_view(), name="game"),
    path("classement/", LeaderboardView.as_view(), name="classement"),

    # API endpoints
    path("api/temperatures", api_temperatures, name="api_temperatures"),
    path("api/start_game", api_start_game, name="api_start_game"),
    path("api/game_status", api_game_status, name="api_game_status"),
]