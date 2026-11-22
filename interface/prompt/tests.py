import json
from unittest import mock

import requests
from django.test import TestCase, override_settings
from django.urls import reverse

from . import reel, simulation
from .contenu import MODELES, PRE_PROMPT, QUESTIONS


@override_settings(VIE_PROMPT_SIMULATION=True)
class VieDuPromptTests(TestCase):
    def setUp(self):
        simulation.reinitialiser()

    def post(self, nom, **data):
        return self.client.post(reverse(nom), json.dumps(data), content_type="application/json")

    def test_pages(self):
        for nom in ("prompt:index", "prompt:commande", "prompt:ecran"):
            self.assertEqual(self.client.get(reverse(nom)).status_code, 200)

    def test_etat_initial(self):
        e = self.client.get(reverse("prompt:api_etat")).json()
        self.assertIsNone(e["run"])
        self.assertFalse(e["en_cours"])
        self.assertEqual(e["charges"], {"1": None, "2": None, "3": None})

    def test_lancer_puis_refus_si_en_cours(self):
        r = self.post("prompt:api_lancer", q=1, pi=2, model="Falcon")
        self.assertEqual(r.status_code, 200)
        e = r.json()
        self.assertTrue(e["en_cours"])
        run = e["run"]
        self.assertEqual((run["q"], run["pi"], run["model"]), (1, 2, "Falcon"))
        types = [ev["type"] for ev in run["evenements"]]
        self.assertEqual(types[0], "sent")
        self.assertEqual(types[-1], "done")
        self.assertIn("load_start", types)  # premier lancement : le modèle doit être chargé
        self.assertEqual(types.count("token"), len(QUESTIONS[1]["a"]))
        self.assertEqual(run["duree"], run["evenements"][-1]["t"])
        self.assertEqual(e["charges"]["2"], "Falcon")
        # une seule génération à la fois
        self.assertEqual(self.post("prompt:api_lancer", q=0, pi=1, model="Gemma").status_code, 409)

    def test_chargement_saute_si_modele_deja_en_ram(self):
        evs = simulation.construire_evenements(0, 1, "Gemma", deja_charge=True)
        types = [e["type"] for e in evs]
        self.assertIn("load_skipped", types)
        self.assertNotIn("load_start", types)
        evs2 = simulation.construire_evenements(0, 1, "Gemma", deja_charge=False)
        self.assertGreater(evs2[-1]["t"] - evs[-1]["t"], MODELES["Gemma"]["load"])
        ts = [e["t"] for e in evs2]
        self.assertEqual(ts, sorted(ts))

    def test_selection(self):
        e = self.post("prompt:api_selection", q=3, pi=3, model="Ministral").json()
        self.assertEqual(e["selection"], {"q": 3, "pi": 3, "model": "Ministral"})

    def test_parametres_invalides(self):
        for data in ({"q": 99, "pi": 1, "model": "Gemma"}, {"q": 0, "pi": 9, "model": "Gemma"},
                     {"q": 0, "pi": 1, "model": "GPT"}, {"q": "x", "pi": 1, "model": "Gemma"}, {}):
            self.assertEqual(self.post("prompt:api_lancer", **data).status_code, 400, data)
            self.assertEqual(self.post("prompt:api_selection", **data).status_code, 400, data)

    def test_tokeniser(self):
        self.assertEqual(simulation.tokeniser("C’est quoi un data center ?"),
                         ["C’est", "quoi", "un", "data", "center", "?"])


class _FauxFlux:
    """Réponse HTTP en streaming d'un faux Raspberry Pi (format Ollama)."""

    def __init__(self, lignes, coupure=False):
        self.lignes, self.coupure, self.ferme = lignes, coupure, False

    def raise_for_status(self):
        pass

    def iter_lines(self, chunk_size=None):
        for ligne in self.lignes:
            yield json.dumps(ligne).encode()
        if self.coupure:
            raise requests.ConnectionError("coupure")

    def close(self):
        self.ferme = True


class _FilSynchrone:
    """Remplace threading.Thread : exécute la génération tout de suite."""

    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@override_settings(VIE_PROMPT_SIMULATION=False)
@mock.patch.object(reel, "AFFICHAGE_ENVOI_S", 0)
@mock.patch.object(reel, "AFFICHAGE_TOKEN_QUESTION_S", 0)
@mock.patch("prompt.simulation.threading.Thread", _FilSynchrone)
class ModeReelTests(TestCase):
    def setUp(self):
        simulation.reinitialiser()

    def lancer(self, **data):
        return self.client.post(reverse("prompt:api_lancer"), json.dumps(data), content_type="application/json")

    def types(self):
        return [e["type"] for e in simulation.etat()["run"]["evenements"]]

    def test_envoi_au_bon_pi_avec_le_bon_modele(self):
        flux = _FauxFlux([{"response": "Oui", "done": False}, {"response": ", souvent.", "done": False},
                          {"response": "", "done": True, "eval_count": 2}])
        with mock.patch("prompt.reel.requests.post", return_value=flux) as post:
            self.assertEqual(self.lancer(q=2, pi=3, model="Ministral").status_code, 200)
        url = post.call_args.args[0]
        payload = post.call_args.kwargs["json"]
        self.assertEqual(url, reel.RASPBERRIES[2]["ollama_url"])
        self.assertEqual(payload["model"], "ministral-3:3b")
        self.assertIn(PRE_PROMPT, payload["prompt"])
        self.assertIn(QUESTIONS[2]["q"], payload["prompt"])
        self.assertTrue(flux.ferme)
        e = simulation.etat()
        self.assertFalse(e["en_cours"])
        self.assertEqual(e["run"]["mode"], "reel")
        self.assertEqual(self.types(), ["sent", "received", "tokenized", "load_start", "loaded",
                                        "generation_start", "token", "token", "generation_end", "done"])
        self.assertEqual("".join(ev["text"] for ev in e["run"]["evenements"] if ev["type"] == "token"), "Oui, souvent.")
        self.assertEqual(e["charges"][3], "Ministral")

    def test_chargement_saute_si_meme_modele_recemment(self):
        flux = lambda: _FauxFlux([{"response": "Ok", "done": False}, {"response": "", "done": True}])
        with mock.patch("prompt.reel.requests.post", side_effect=[flux(), flux()]):
            self.lancer(q=0, pi=1, model="Gemma")
            self.lancer(q=1, pi=1, model="Gemma")
        self.assertIn("load_skipped", self.types())
        self.assertNotIn("load_start", self.types())

    def test_pi_injoignable(self):
        with mock.patch("prompt.reel.requests.post", side_effect=requests.ConnectionError("non")):
            self.lancer(q=0, pi=2, model="Gemma")
        e = simulation.etat()
        self.assertFalse(e["en_cours"])
        self.assertEqual(self.types(), ["sent", "error"])
        self.assertIn("Pi 2", e["run"]["evenements"][-1]["message"])

    def test_erreur_ollama(self):
        with mock.patch("prompt.reel.requests.post", return_value=_FauxFlux([{"error": "model not found"}])):
            self.lancer(q=0, pi=1, model="Falcon")
        self.assertEqual(self.types()[-1], "error")
        self.assertFalse(simulation.etat()["en_cours"])

    def test_coupure_en_cours_de_reponse(self):
        flux = _FauxFlux([{"response": "Début", "done": False}], coupure=True)
        with mock.patch("prompt.reel.requests.post", return_value=flux):
            self.lancer(q=0, pi=1, model="Gemma")
        toks = [ev["text"] for ev in simulation.etat()["run"]["evenements"] if ev["type"] == "token"]
        self.assertEqual(toks, ["Début", " […]"])
        self.assertEqual(self.types()[-1], "done")

    def test_reponse_trop_longue_coupee(self):
        lignes = [{"response": " mot", "done": False}] * (reel.MAX_TOKENS + 50)
        with mock.patch("prompt.reel.requests.post", return_value=_FauxFlux(lignes)):
            self.lancer(q=0, pi=1, model="Gemma")
        self.assertEqual(self.types().count("token"), reel.MAX_TOKENS + 1)

    def test_metriques(self):
        rep = mock.Mock(**{"json.return_value": {"temperature_c": 61.2, "ram_used_percent": 47.0,
                                                 "cpu_load_percent": {"avg": 88.5}, "cpu_freq_mhz": 1800}})
        with mock.patch("prompt.reel.requests.get", return_value=rep) as get:
            m = self.client.get(reverse("prompt:api_metriques"), {"pi": 2}).json()
        self.assertEqual(get.call_args.args[0], reel.RASPBERRIES[1]["temp_url"])
        self.assertEqual(m, {"ok": True, "temperature_c": 61.2, "ram_used_percent": 47.0,
                             "cpu_load_percent": 88.5, "cpu_freq_mhz": 1800})
        with mock.patch("prompt.reel.requests.get", side_effect=requests.Timeout()):
            self.assertEqual(self.client.get(reverse("prompt:api_metriques"), {"pi": 2}).json(), {"ok": False})
        self.assertEqual(self.client.get(reverse("prompt:api_metriques"), {"pi": 7}).status_code, 400)
