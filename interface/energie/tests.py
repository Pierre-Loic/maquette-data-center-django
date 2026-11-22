import json
import threading
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from . import moteur
from .contenu import LONGUEURS, QUESTIONS


def faux_ollama(rpi, prompt, model, on_progress=None):
    """Faux Raspberry Pi : renvoie une réponse dont la durée dépend du Pi."""
    nom = rpi["name"]
    if on_progress:
        on_progress(nom, "Début", 1)
    return nom, f"Réponse de {nom} ({model})", 42, 3.5


def _synchrone(fonction, *args):
    fonction(*args)


class EnergieTests(TestCase):
    def setUp(self):
        moteur.reinitialiser()

    def lancer(self, **data):
        return self.client.post(reverse("energie:api_lancer"), json.dumps(data), content_type="application/json")

    def test_page(self):
        self.assertEqual(self.client.get(reverse("energie:index")).status_code, 200)

    def test_prompt_construit(self):
        self.assertEqual(moteur.construire_prompt(1, "courte"),
                         f"{QUESTIONS[1]['prompt']} {LONGUEURS['courte']['consigne']}")

    @mock.patch("energie.moteur._en_arriere_plan", _synchrone)
    @mock.patch("energie.moteur.call_ollama", side_effect=faux_ollama)
    def test_envoi_aux_3_pi(self, ollama):
        r = self.lancer(q=2, model="Falcon", longueur="longue")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(ollama.call_count, 3)
        prompts = {c.args[1] for c in ollama.call_args_list}
        modeles = {c.args[2] for c in ollama.call_args_list}
        self.assertEqual(prompts, {moteur.construire_prompt(2, "longue")})
        self.assertEqual(modeles, {"falcon3:1b"})
        e = moteur.etat()
        self.assertFalse(e["en_cours"])
        self.assertTrue(e["en_mesure"])  # mesure de la température après la génération
        for nom, p in e["run"]["pis"].items():
            self.assertTrue(p["fini"])
            self.assertEqual((p["tokens"], p["secondes"]), (42, 3.5))
            self.assertIn(nom, p["texte"])
        self.assertIsNotNone(e["run"]["fin"])

    def test_une_generation_a_la_fois(self):
        liberer, appels = threading.Event(), threading.Semaphore(0)

        def lent(rpi, prompt, model, on_progress=None):
            appels.release()
            liberer.wait(5)
            return rpi["name"], "ok", 1, 1.0

        with mock.patch("energie.moteur.call_ollama", side_effect=lent):
            self.assertEqual(self.lancer(q=0, model="Gemma", longueur="courte").status_code, 200)
            for _ in range(3):  # les 3 Pi sont en train de générer
                self.assertTrue(appels.acquire(timeout=5))
            self.assertTrue(moteur.etat()["en_cours"])
            self.assertEqual(self.lancer(q=1, model="Gemma", longueur="courte").status_code, 409)
            liberer.set()
            for _ in range(100):  # attend la fin avant de retirer le faux Pi
                if not moteur.etat()["en_cours"]:
                    break
                threading.Event().wait(0.05)
        self.assertFalse(moteur.etat()["en_cours"])

    def test_parametres_invalides(self):
        for d in ({"q": 9, "model": "Gemma", "longueur": "courte"}, {"q": 0, "model": "GPT", "longueur": "courte"},
                  {"q": 0, "model": "Gemma", "longueur": "infinie"}, {}):
            self.assertEqual(self.lancer(**d).status_code, 400, d)

    @mock.patch("energie.moteur._en_arriere_plan", _synchrone)
    @mock.patch("energie.moteur.call_ollama", side_effect=faux_ollama)
    def test_temperature_max_pendant_la_generation(self, _):
        self.lancer(q=0, model="Gemma", longueur="courte")
        # deux mesures successives pour chacun des 3 Pi (lus en parallèle)
        series = {1: [50.0, 55.0], 2: [61.0, 59.0], 3: [48.0, 47.0]}
        with mock.patch("energie.moteur.metriques",
                        side_effect=lambda pi: {"ok": True, "temperature_c": series[pi].pop(0)}):
            self.client.get(reverse("energie:api_mesures"))
            m = self.client.get(reverse("energie:api_mesures")).json()
        self.assertEqual(len(m["pis"]), 3)
        maxi = [p["temp_max"] for p in moteur.etat()["run"]["pis"].values()]
        self.assertEqual(maxi, [55.0, 61.0, 48.0])
