import json
from unittest import mock

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


class MedicalViewTest(TestCase):
    """Tests pour le comparateur médical"""

    def test_page_renders_with_questions_and_models(self):
        response = self.client.get(reverse("medical"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/medical.html")
        self.assertContains(response, "medgemma:4b")
        self.assertContains(response, "falcon3:1b")
        self.assertContains(response, 'id="medical-questions"')

    def test_page_has_back_button_and_no_header_banner(self):
        response = self.client.get(reverse("medical"))
        self.assertContains(response, 'id="backBtn"')
        self.assertContains(response, 'href="/"')
        self.assertNotContains(response, "Plateforme pédagogique sur l'IA générative")
        self.assertNotContains(response, "questionChips")
        self.assertContains(response, 'id="questionSelect"')

    def test_gemma3_4b_is_default_general_model(self):
        response = self.client.get(reverse("medical"))
        self.assertEqual(response.context["general_models"][0][0], "gemma3:4b")

    def test_stream_rejects_empty_question(self):
        response = self.client.get(reverse("api_medical_stream"), {"question": "  "})
        self.assertEqual(response.status_code, 400)

    def test_stream_rejects_too_long_question(self):
        response = self.client.get(reverse("api_medical_stream"), {"question": "x" * 1001})
        self.assertEqual(response.status_code, 400)

    def test_stream_rejects_unknown_general_model(self):
        response = self.client.get(
            reverse("api_medical_stream"),
            {"question": "Q ?", "general_model": "modele-inconnu:7b"},
        )
        self.assertEqual(response.status_code, 400)

    def _events(self, response):
        raw = b"".join(response.streaming_content).decode()
        return [json.loads(line[6:]) for line in raw.split("\n\n") if line.startswith("data: ")]

    def test_stream_runs_both_models_on_distinct_pis(self):
        calls = []

        def fake_call_ollama(rpi, prompt, model, on_progress=None, max_tokens=None, should_stop=None):
            calls.append((rpi["name"], model, prompt, max_tokens))
            return rpi["name"], f"réponse {model}", 12, 1.5

        with mock.patch("dashboard.views.call_ollama", fake_call_ollama):
            response = self.client.get(
                reverse("api_medical_stream"),
                {"question": "Qu'est-ce que le TMB ?", "general_model": "llama3.2:1b"},
            )
            events = self._events(response)

        self.assertEqual({c[1] for c in calls}, {"llama3.2:1b", "medgemma:4b"})
        self.assertEqual(len({c[0] for c in calls}), 2)
        self.assertTrue(all("Qu'est-ce que le TMB ?" in c[2] for c in calls))
        self.assertEqual(events[0]["type"], "start")
        self.assertEqual(events[-1]["type"], "all_done")
        done = {e["side"]: e for e in events if e["type"] == "done"}
        self.assertEqual(done["general"]["text"], "réponse llama3.2:1b")
        self.assertEqual(done["specialist"]["text"], "réponse medgemma:4b")
        self.assertFalse(done["specialist"]["error"])

    def test_stream_flags_failed_model(self):
        def fake_call_ollama(rpi, prompt, model, **kwargs):
            if model == "medgemma:4b":
                return rpi["name"], "🔥🤯 Surchauffe !!", 0, 1.0
            return rpi["name"], "ok", 3, 1.0

        with mock.patch("dashboard.views.call_ollama", fake_call_ollama):
            events = self._events(self.client.get(reverse("api_medical_stream"), {"question": "Q ?"}))

        done = {e["side"]: e for e in events if e["type"] == "done"}
        self.assertTrue(done["specialist"]["error"])
        self.assertEqual(done["specialist"]["text"], "")
        self.assertFalse(done["general"]["error"])
