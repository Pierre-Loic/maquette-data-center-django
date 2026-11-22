from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Accueil du stand SEPEM + 4 activités
    path("", include("salon.urls")),
    path("histoire/", include("histoire.urls")),
    path("energie/", include("energie.urls")),
    path("prompt/", include("prompt.urls")),
    path("agentique/", include("agentique.urls")),
    # Maquette data center (jeu, dialogue, classement…)
    path("", include("dashboard.urls")),
    path("admin/", admin.site.urls),
]
