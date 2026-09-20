from django.urls import path
from .views import (
    LeaderboardView,
    HomeView,
    GameView,
    DialogueView,
    MedicalView,
    api_temperatures,
    api_start_game,
    api_game_stream,
    api_game_status,
    api_dialogue_next,
    api_medical_stream,
    api_power,
)

urlpatterns = [
    path("", GameView.as_view(), name="game"),
    path("fonctionnement/", HomeView.as_view(), name="fonctionnement"),
    path("classement/", LeaderboardView.as_view(), name="classement"),
    path("dialogue/", DialogueView.as_view(), name="dialogue"),
    path("medical/", MedicalView.as_view(), name="medical"),

    # API endpoints
    path("api/temperatures", api_temperatures, name="api_temperatures"),
    path("api/start_game", api_start_game, name="api_start_game"),
    path("api/game_stream", api_game_stream, name="api_game_stream"),
    path("api/game_status", api_game_status, name="api_game_status"),
    path("api/dialogue_next", api_dialogue_next, name="api_dialogue_next"),
    path("api/medical_stream", api_medical_stream, name="api_medical_stream"),
    path("api/power", api_power, name="api_power"),
]