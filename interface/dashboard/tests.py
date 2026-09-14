from django.test import TestCase, Client
from django.urls import reverse
from .models import LeaderboardEntry


class LeaderboardEntryModelTest(TestCase):
    """Tests pour le modèle LeaderboardEntry"""

    def setUp(self):
        self.entry = LeaderboardEntry.objects.create(
            pseudo="TestPlayer",
            points=25,
            predicted_temp_pi1=45.0,
            predicted_temp_pi2=40.0,
            predicted_temp_pi3=35.0,
            max_temp_pi1=46.5,
            max_temp_pi2=41.2,
            max_temp_pi3=36.8,
            prompt="Test prompt",
            answer_pi1="Réponse 1",
            answer_pi2="Réponse 2",
            answer_pi3="Réponse 3",
        )

    def test_entry_creation(self):
        """Test la création d'une entrée au classement"""
        self.assertEqual(self.entry.pseudo, "TestPlayer")
        self.assertEqual(self.entry.points, 25)

    def test_str_representation(self):
        """Test la représentation string du modèle"""
        self.assertEqual(str(self.entry), "TestPlayer — 25 pts")

    def test_predicted_temps_property(self):
        """Test la propriété predicted_temps"""
        temps = self.entry.predicted_temps
        self.assertEqual(temps["Refroidissement passif air"], 45.0)
        self.assertEqual(temps["Refroidissement actif air"], 40.0)
        self.assertEqual(temps["Refroidissement actif eau"], 35.0)

    def test_max_temps_property(self):
        """Test la propriété max_temps"""
        temps = self.entry.max_temps
        self.assertEqual(temps["Refroidissement passif air"], 46.5)
        self.assertEqual(temps["Refroidissement actif air"], 41.2)
        self.assertEqual(temps["Refroidissement actif eau"], 36.8)

    def test_ordering(self):
        """Test l'ordre par défaut (points décroissants)"""
        LeaderboardEntry.objects.create(pseudo="Player2", points=30, prompt="p")
        LeaderboardEntry.objects.create(pseudo="Player3", points=10, prompt="p")

        entries = list(LeaderboardEntry.objects.all())
        self.assertEqual(entries[0].pseudo, "Player2")
        self.assertEqual(entries[1].pseudo, "TestPlayer")
        self.assertEqual(entries[2].pseudo, "Player3")


class HomeViewTest(TestCase):
    """Tests pour la vue Home"""

    def test_home_page_status_code(self):
        """Test que la page d'accueil retourne un code 200"""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_home_page_uses_correct_template(self):
        """Test que la page d'accueil utilise le bon template"""
        response = self.client.get("/")
        self.assertTemplateUsed(response, "dashboard/fonctionnement.html")
