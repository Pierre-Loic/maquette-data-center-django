from django.db import models
from django.core.validators import MinValueValidator

class LeaderboardEntry(models.Model):
    pseudo = models.CharField(max_length=50, db_index=True)
    points = models.IntegerField(default=0, validators=[MinValueValidator(0)], db_index=True)

    # Predictions (°C)
    predicted_temp_pi1 = models.FloatField(null=True, blank=True)
    predicted_temp_pi2 = models.FloatField(null=True, blank=True)
    predicted_temp_pi3 = models.FloatField(null=True, blank=True)

    # Max temperatures (°C)
    max_temp_pi1 = models.FloatField(null=True, blank=True)
    max_temp_pi2 = models.FloatField(null=True, blank=True)
    max_temp_pi3 = models.FloatField(null=True, blank=True)

    # Prompt and answers
    prompt = models.TextField()
    answer_pi1 = models.TextField(null=True, blank=True)
    answer_pi2 = models.TextField(null=True, blank=True)
    answer_pi3 = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-points", "created_at"]
        indexes = [
            models.Index(fields=["-points", "created_at"]),
            models.Index(fields=["pseudo", "-points"]),
        ]

    def __str__(self) -> str:
        return f"{self.pseudo} — {self.points} pts"

    @property
    def predicted_temps(self):
        return {
            "Passive air cooling": self.predicted_temp_pi1,
            "Active air cooling": self.predicted_temp_pi2,
            "Active water cooling": self.predicted_temp_pi3,
        }

    @property
    def max_temps(self):
        return {
            "Passive air cooling": self.max_temp_pi1,
            "Active air cooling": self.max_temp_pi2,
            "Active water cooling": self.max_temp_pi3,
        }

    @property
    def answers(self):
        return {
            "Passive air cooling": self.answer_pi1,
            "Active air cooling": self.answer_pi2,
            "Active water cooling": self.answer_pi3,
        }
