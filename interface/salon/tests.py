import json
import threading
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from agentique import moteur as agent
from energie import moteur as energie
from prompt import simulation as prompt


def post(client, nom, **data):
    return client.post(reverse(nom), json.dumps(data), content_type="application/json")


@override_settings(VIE_PROMPT_SIMULATION=True)
@mock.patch("agentique.moteur.lire_temperatures", return_value={1: 40.0, 2: 41.0, 3: 39.0})
class RetourAccueilTests(TestCase):
    """Revenir sur l'accueil remet les activités dans leur configuration initiale."""

    def setUp(self):
        prompt.reinitialiser()
        energie.reinitialiser()
        agent.reinitialiser()

    def test_accueil(self, _):
        self.assertEqual(self.client.get(reverse("salon:accueil")).status_code, 200)

    def test_mission_en_attente_de_validation_oubliee(self, _):
        post(self.client, "agentique:api_lancer", mission="commande", autonomie="valider")
        self.assertIsNotNone(agent.etat()["attente"])
        self.client.get(reverse("salon:accueil"))
        self.assertIsNone(agent.etat()["run"])

    def test_generation_terminee_oubliee_modeles_en_ram_conserves(self, _):
        post(self.client, "prompt:api_lancer", q=0, pi=2, model="Falcon")
        with mock.patch("prompt.simulation.maintenant_ms", return_value=prompt.maintenant_ms() + 10**6):
            self.client.get(reverse("salon:accueil"))
        e = prompt.etat()
        self.assertIsNone(e["run"])
        self.assertEqual(e["charges"][2], "Falcon")

    def test_generation_en_cours_conservee(self, _):
        post(self.client, "prompt:api_lancer", q=0, pi=1, model="Gemma")
        self.client.get(reverse("salon:accueil"))
        self.assertIsNotNone(prompt.etat()["run"])

    def test_energie(self, _):
        liberer = threading.Event()

        def lent(rpi, prompt_, model, on_progress=None):
            liberer.wait(5)
            return rpi["name"], "ok", 1, 1.0

        with mock.patch("energie.moteur.call_ollama", side_effect=lent):
            post(self.client, "energie:api_lancer", q=0, model="Gemma", longueur="courte")
            self.client.get(reverse("salon:accueil"))
            self.assertIsNotNone(energie.etat()["run"])  # en cours : conservée
            liberer.set()
            for _ in range(100):
                if not energie.etat()["en_cours"]:
                    break
                threading.Event().wait(0.05)
        self.client.get(reverse("salon:accueil"))
        self.assertIsNone(energie.etat()["run"])
