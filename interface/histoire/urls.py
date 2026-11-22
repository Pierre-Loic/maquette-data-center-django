from django.urls import path

from .views import IndexView, api_classement, api_score

app_name = "histoire"

urlpatterns = [
    path("", IndexView.as_view(), name="index"),
    path("api/classement", api_classement, name="api_classement"),
    path("api/score", api_score, name="api_score"),
]
