from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

# Clés des thématiques : doivent correspondre aux clés de THEMES dans
# static/histoire/js/frise_contenu.js
THEMES = {
    "biz": "Modèle d’affaire",
    "tech": "Technique",
    "bia": "Biais",
    "env": "Environnement",
}

# Durée maximale d'une partie (doit correspondre à REGLAGES.dureeSecondes)
DUREE_MAX_MS = 240_000


class FriseScore(models.Model):
    """Une partie gagnée du jeu « La Frise de l'IA »."""

    pseudo = models.CharField(max_length=20)
    theme = models.CharField(max_length=10, choices=THEMES.items(), db_index=True)
    # Temps total en millisecondes, pénalités comprises : c'est le score (plus bas = mieux)
    temps_ms = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(DUREE_MAX_MS)]
    )
    erreurs = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["temps_ms", "erreurs", "created_at"]
        indexes = [models.Index(fields=["theme", "temps_ms", "erreurs", "created_at"])]
        verbose_name = "score de la frise"
        verbose_name_plural = "scores de la frise"

    def __str__(self) -> str:
        s = self.temps_ms // 1000
        return f"{self.pseudo} — {self.get_theme_display()} — {s // 60}:{s % 60:02d}"
