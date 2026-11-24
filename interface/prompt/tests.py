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
        # lecture du prompt puis génération, dans cet ordre
        self.assertLess(types.index("prefill_start"), types.index("prefill_end"))
        self.assertLess(types.index("prefill_end"), types.index("generation_start"))
        self.assertLess(types.index("generation_start"), types.index("token"))
        fin = next(ev for ev in run["evenements"] if ev["type"] == "generation_end")["stats"]
        self.assertEqual(fin["gen_tokens"], len(QUESTIONS[1]["a"]))
        self.assertGreater(fin["prompt_tokens"], 10)  # pré-prompt + question
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
        self.assertGreater(evs2[-1]["t"] - evs[-1]["t"], MODELES["Gemma"]["load"] * 0.8)
        ts = [e["t"] for e in evs2]
        self.assertEqual(ts, sorted(ts))

    def test_simulation_pre_prompt_cache_et_cache(self):
        froid = simulation.construire_evenements(0, 3, "Ministral", deja_charge=False)
        chaud = simulation.construire_evenements(0, 3, "Ministral", deja_charge=True)
        st = lambda evs: next(e for e in evs if e["type"] == "generation_end")["stats"]
        self.assertEqual(st(froid)["prompt_cached"], 0)
        self.assertGreater(st(chaud)["prompt_cached"], 552)
        self.assertGreater(st(froid)["prompt_ms"], 20 * st(chaud)["prompt_ms"])  # lecture bien plus longue sans cache
        self.assertEqual(next(e for e in froid if e["type"] == "tokenized")["n_cache"], 552)

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


def _synchrone(fonction, *args):
    """Exécute la génération tout de suite (au lieu d'un fil séparé)."""
    fonction(*args)


class _Reponse:
    """Réponse simple (non streaming) d'Ollama."""

    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data

    def close(self):
        pass


def _flux_ollama(textes, prompt_tokens=41, prompt_ns=120_000_000, gen_ns=1_500_000_000, done_reason="stop", cached=0):
    """Flux d'Ollama : un token par ligne, puis les durées mesurées."""
    lignes = [{"model": "m", "response": t, "done": False} for t in textes]
    lignes.append({"model": "m", "response": "", "done": True, "done_reason": done_reason,
                   "prompt_eval_count": prompt_tokens, "prompt_eval_cached_count": cached, "prompt_eval_duration": prompt_ns,
                   "eval_count": len(textes), "eval_duration": gen_ns})
    return _FauxFlux(lignes)


@override_settings(VIE_PROMPT_SIMULATION=False)
@mock.patch.object(reel, "AFFICHAGE_ENVOI_S", 0)
@mock.patch.object(reel, "AFFICHAGE_TOKEN_QUESTION_S", 0)
@mock.patch.object(reel, "AFFICHAGE_APRES_CHARGEMENT_S", 0)
@mock.patch.object(reel, "AFFICHAGE_LECTURE_S", 0)
@mock.patch.object(reel, "AFFICHAGE_PREPROMPT_CACHE_S", 0)
@mock.patch.object(reel, "AFFICHAGE_MOT_S", 0)
@mock.patch("prompt.simulation._en_arriere_plan", _synchrone)
class ModeReelOllamaTests(TestCase):
    """Vrais Pi, en parlant directement à Ollama (streaming + durées exactes)."""

    def setUp(self):
        simulation.reinitialiser()

    def lancer(self, en_ram=(), **data):
        with mock.patch("prompt.reel.modeles_en_ram", return_value=list(en_ram)):
            return self.client.post(reverse("prompt:api_lancer"), json.dumps(data), content_type="application/json")

    def evs(self):
        return simulation.etat()["run"]["evenements"]

    def types(self):
        return [e["type"] for e in self.evs()]

    def test_chargement_lecture_puis_generation(self):
        flux = _flux_ollama(["L’IA", " peut", " se", " tromper."])
        with mock.patch("prompt.reel.requests.post", side_effect=[_Reponse({"done": True}), flux]) as post:
            self.assertEqual(self.lancer(q=0, pi=2, model="Falcon").status_code, 200)
        (url1,), k1 = post.call_args_list[0]
        (url2,), k2 = post.call_args_list[1]
        self.assertTrue(url1.endswith(":11434/api/generate"))
        self.assertNotIn("prompt", k1["json"])                       # chargement seul
        self.assertEqual(k1["json"]["model"], "falcon3:1b")
        self.assertEqual(k2["json"]["options"]["num_predict"], reel.MAX_TOKENS)
        self.assertIn(PRE_PROMPT, k2["json"]["prompt"])
        self.assertTrue(k2["json"]["stream"])
        self.assertEqual(self.types(), ["sent", "received", "tokenized", "load_start", "loaded", "prefill_start",
                                        "prefill_end", "generation_start", "token", "token", "token", "token",
                                        "generation_end", "done"])
        stats = next(e for e in self.evs() if e["type"] == "generation_end")["stats"]
        self.assertEqual(stats, {"prompt_tokens": 41, "prompt_cached": 0, "prompt_ms": 120, "gen_tokens": 4, "gen_ms": 1500})
        self.assertTrue(all("tr" in e for e in self.evs() if e["type"] == "token"))
        e = simulation.etat()
        self.assertFalse(e["en_cours"])
        self.assertEqual(e["charges"][2], "Falcon")

    def test_pre_prompt_cache_de_ministral(self):
        """Ministral ajoute ~550 tokens de consignes de Mistral AI : affichés au découpage,
        et la part déjà en cache est remontée à la fin."""
        flux = _flux_ollama(["Oui."], prompt_tokens=599, cached=590)
        with mock.patch("prompt.reel.requests.post", return_value=flux):
            self.lancer(en_ram=["ministral-3:3b"], q=0, pi=3, model="Ministral")
        dec = next(e for e in self.evs() if e["type"] == "tokenized")
        self.assertEqual((dec["n_cache"], dec["fournisseur"]), (552, "Mistral AI"))
        self.assertGreater(dec["n_prompt"], 552)
        stats = next(e for e in self.evs() if e["type"] == "generation_end")["stats"]
        self.assertEqual((stats["prompt_tokens"], stats["prompt_cached"]), (599, 590))

    def test_pas_de_pre_prompt_cache_pour_gemma(self):
        with mock.patch("prompt.reel.requests.post", return_value=_flux_ollama(["Oui."])):
            self.lancer(en_ram=["gemma3:270m"], q=0, pi=1, model="Gemma")
        self.assertEqual(next(e for e in self.evs() if e["type"] == "tokenized")["n_cache"], 0)

    def test_modele_deja_en_ram(self):
        with mock.patch("prompt.reel.requests.post", return_value=_flux_ollama(["Oui."])) as post:
            self.lancer(en_ram=["gemma3:270m"], q=0, pi=1, model="Gemma")
        self.assertEqual(post.call_count, 1)  # pas de chargement
        self.assertIn("load_skipped", self.types())
        self.assertNotIn("load_start", self.types())

    def test_reponse_coupee_a_max_tokens(self):
        flux = _flux_ollama(["mot"] * 5, done_reason="length")
        with mock.patch("prompt.reel.requests.post", return_value=flux):
            self.lancer(en_ram=["gemma3:270m"], q=0, pi=1, model="Gemma")
        toks = [e["text"] for e in self.evs() if e["type"] == "token"]
        self.assertEqual(toks[-1], " […]")

    def test_modele_absent_du_pi(self):
        with mock.patch("prompt.reel.requests.post", return_value=_Reponse({"error": "model not found"})):
            self.lancer(q=0, pi=1, model="Ministral")
        self.assertEqual(self.types()[-2:], ["load_start", "error"])
        self.assertIn("pas disponible", self.evs()[-1]["message"])
        self.assertFalse(simulation.etat()["en_cours"])

    def test_coupure_pendant_la_generation(self):
        flux = _FauxFlux([{"response": "Début", "done": False}], coupure=True)
        with mock.patch("prompt.reel.requests.post", return_value=flux):
            self.lancer(en_ram=["gemma3:270m"], q=0, pi=1, model="Gemma")
        self.assertEqual([e["text"] for e in self.evs() if e["type"] == "token"], ["Début", " […]"])
        self.assertEqual(self.types()[-1], "done")


@override_settings(VIE_PROMPT_SIMULATION=False)
@mock.patch.object(reel, "AFFICHAGE_ENVOI_S", 0)
@mock.patch.object(reel, "AFFICHAGE_TOKEN_QUESTION_S", 0)
@mock.patch.object(reel, "AFFICHAGE_APRES_CHARGEMENT_S", 0)
@mock.patch.object(reel, "AFFICHAGE_LECTURE_S", 0)
@mock.patch.object(reel, "AFFICHAGE_PREPROMPT_CACHE_S", 0)
@mock.patch.object(reel, "AFFICHAGE_MOT_S", 0)
@mock.patch("prompt.simulation._en_arriere_plan", _synchrone)
class ModeReelTests(TestCase):
    """Secours : Ollama injoignable, on passe par l'API FastAPI du Pi."""

    def setUp(self):
        simulation.reinitialiser()
        p = mock.patch("prompt.reel.modeles_en_ram", return_value=None)
        p.start()
        self.addCleanup(p.stop)

    def lancer(self, joignable=True, **data):
        with mock.patch("prompt.reel.metriques", return_value={"ok": joignable}):
            return self.client.post(reverse("prompt:api_lancer"), json.dumps(data), content_type="application/json")

    def types(self):
        return [e["type"] for e in simulation.etat()["run"]["evenements"]]

    def texte(self):
        return "".join(e["text"] for e in simulation.etat()["run"]["evenements"] if e["type"] == "token")

    def test_reponse_en_bloc(self):
        flux = lambda: _FauxFlux([{"device": "rpi-3", "model": "ministral-3:3b", "response": "Oui, elle peut se tromper.\n"}])
        with mock.patch("prompt.reel.requests.post", side_effect=[flux(), flux()]) as post:
            self.assertEqual(self.lancer(q=2, pi=3, model="Ministral").status_code, 200)
        (url1,), k1 = post.call_args_list[0]
        (url2,), k2 = post.call_args_list[1]
        self.assertEqual(url1, reel.RASPBERRIES[2]["ollama_url"])
        self.assertEqual(k1["json"], {"prompt": reel.PROMPT_CHARGEMENT, "model": "ministral-3:3b"})
        self.assertEqual(url2, url1)
        self.assertIn(PRE_PROMPT, k2["json"]["prompt"])
        self.assertEqual(self.types(), ["sent", "received", "tokenized", "load_start", "loaded", "prefill_start",
                                        "prefill_end", "generation_start", "token", "token", "token", "token",
                                        "token", "generation_end", "done"])
        fin = next(e for e in simulation.etat()["run"]["evenements"] if e["type"] == "generation_end")
        self.assertIn("total_ms", fin["stats"])
        self.assertEqual(self.texte(), "Oui, elle peut se tromper.")
        self.assertEqual(simulation.etat()["charges"][3], "Ministral")

    def test_flux_token_par_token(self):
        flux = _FauxFlux([{"response": "Oui", "done": False}, {"response": ", souvent.", "done": False},
                          {"response": "", "done": True, "eval_count": 2}])
        with mock.patch("prompt.reel.requests.post", return_value=flux):
            self.lancer(q=0, pi=1, model="Gemma")
        self.assertEqual(self.types(), ["sent", "received", "tokenized", "load_start", "loaded", "prefill_start",
                                        "prefill_end", "generation_start", "token", "token", "generation_end", "done"])
        self.assertEqual(self.texte(), "Oui, souvent.")

    def test_chargement_saute_si_meme_modele_recemment(self):
        flux = lambda: _FauxFlux([{"response": "Ok."}])
        with mock.patch("prompt.reel.requests.post", side_effect=[flux(), flux(), flux()]) as post:
            self.lancer(q=0, pi=1, model="Gemma")
            self.lancer(q=1, pi=1, model="Gemma")
        self.assertEqual(post.call_count, 3)  # pas de requête de chargement la 2e fois
        self.assertIn("load_skipped", self.types())

    def test_pi_injoignable(self):
        with mock.patch("prompt.reel.requests.post") as post:
            self.lancer(joignable=False, q=0, pi=2, model="Gemma")
        post.assert_not_called()
        self.assertEqual(self.types(), ["sent", "error"])
        self.assertIn("Pi 2", simulation.etat()["run"]["evenements"][-1]["message"])

    def test_echec_du_chargement(self):
        with mock.patch("prompt.reel.requests.post", side_effect=requests.ConnectionError("non")):
            self.lancer(q=0, pi=1, model="Falcon")
        self.assertEqual(self.types()[-2:], ["load_start", "error"])

    def test_reponse_trop_longue_coupee(self):
        long = " ".join(["mot"] * (reel.MAX_TOKENS + 30))
        with mock.patch("prompt.reel.requests.post", return_value=_FauxFlux([{"response": long}])):
            self.lancer(q=0, pi=1, model="Gemma")
        self.assertEqual(self.types().count("token"), reel.MAX_TOKENS + 1)
        self.assertTrue(self.texte().endswith("[…]"))

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
