from django.contrib import admin

from .models import FriseScore


@admin.register(FriseScore)
class FriseScoreAdmin(admin.ModelAdmin):
    """Permet de consulter les scores et de supprimer un pseudo inapproprié."""

    list_display = ("pseudo", "theme", "temps_ms", "erreurs", "created_at")
    list_filter = ("theme", "created_at")
    search_fields = ("pseudo",)
    date_hierarchy = "created_at"
