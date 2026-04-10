from django.test import TestCase, Client
from django.urls import reverse
from .models import LeaderboardEntry


class LeaderboardEntryModelTest(TestCase):
    """Tests for the LeaderboardEntry model"""

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
            answer_pi1="Answer 1",
            answer_pi2="Answer 2",
            answer_pi3="Answer 3",
        )

    def test_entry_creation(self):
        """Test leaderboard entry creation"""
        self.assertEqual(self.entry.pseudo, "TestPlayer")
        self.assertEqual(self.entry.points, 25)

    def test_str_representation(self):
        """Test model string representation"""
        self.assertEqual(str(self.entry), "TestPlayer — 25 pts")

    def test_predicted_temps_property(self):
        """Test predicted_temps property"""
        temps = self.entry.predicted_temps
        self.assertEqual(temps["Passive air cooling"], 45.0)
        self.assertEqual(temps["Active air cooling"], 40.0)
        self.assertEqual(temps["Active water cooling"], 35.0)

    def test_max_temps_property(self):
        """Test max_temps property"""
        temps = self.entry.max_temps
        self.assertEqual(temps["Passive air cooling"], 46.5)
        self.assertEqual(temps["Active air cooling"], 41.2)
        self.assertEqual(temps["Active water cooling"], 36.8)

    def test_ordering(self):
        """Test default ordering (points descending)"""
        LeaderboardEntry.objects.create(pseudo="Player2", points=30, prompt="p")
        LeaderboardEntry.objects.create(pseudo="Player3", points=10, prompt="p")

        entries = list(LeaderboardEntry.objects.all())
        self.assertEqual(entries[0].pseudo, "Player2")
        self.assertEqual(entries[1].pseudo, "TestPlayer")
        self.assertEqual(entries[2].pseudo, "Player3")


class HomeViewTest(TestCase):
    """Tests for the Home view"""

    def test_home_page_status_code(self):
        """Test that the home page returns a 200 status code"""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_home_page_uses_correct_template(self):
        """Test that the home page uses the correct template"""
        response = self.client.get("/")
        self.assertTemplateUsed(response, "dashboard/fonctionnement.html")
