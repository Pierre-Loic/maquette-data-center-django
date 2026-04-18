from django.urls import path
from .views import (
    LeaderboardView,
    HomeView,
    GameView,
    DialogueView,
    api_temperatures,
    api_start_game,
    api_game_status,
    api_dialogue_next,
    api_power,
)

urlpatterns = [
    path("", GameView.as_view(), name="game"),
    path("fonctionnement/", HomeView.as_view(), name="fonctionnement"),
    path("classement/", LeaderboardView.as_view(), name="classement"),
    path("dialogue/", DialogueView.as_view(), name="dialogue"),

    # API endpoints
    path("api/temperatures", api_temperatures, name="api_temperatures"),
    path("api/start_game", api_start_game, name="api_start_game"),
    path("api/game_status", api_game_status, name="api_game_status"),
    path("api/dialogue_next", api_dialogue_next, name="api_dialogue_next"),
    path("api/power", api_power, name="api_power"),
]