import json
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from . import moteur
from .scenarios import SCENARIOS, SEUIL_ALERTE_C


def types(e):
    return [ev["type"] for ev in e["run"]["evenements"]]


def reponse(e):
    return "".join(ev["text"] for ev in e["run"]["evenements"] if ev["type"] == "token")


@mock.patch("agentique.moteur.lire_temperatures", return_value={1: 45.0, 2: 52.0, 3: 39.0})
class AgentTests(TestCase):
    def setUp(self):
        moteur.reinitialiser()

    def post(self, nom, **data):
        return self.client.post(reverse(nom), json.dumps(data), content_type="application/json")

    def test_page(self, _):
        self.assertEqual(self.client.get(reverse("agentique:index")).status_code, 200)

    def test_toutes_les_missions_vont_au_bout_en_autonome(self, _):
        for mission in SCENARIOS:
            moteur.reinitialiser()
            e = self.post("agentique:api_lancer", mission=mission, autonomie="autonome").json()
            self.assertIsNone(e["attente"], mission)
            self.assertEqual(types(e)[0], "sent")
            self.assertEqual(types(e)[-1], "done")
            self.assertTrue(reponse(e), mission)
            ts = [ev["t"] for ev in e["run"]["evenements"]]
            self.assertEqual(ts, sorted(ts), mission)

    def test_validation_humaine_puis_accord(self, _):
        e = self.post("agentique:api_lancer", mission="vibration", autonomie="valider").json()
        self.assertEqual(types(e)[-1], "validation")
        self.assertIn("ticket", e["attente"]["action"])
        self.assertFalse(e["en_cours"])
        # pendant l'attente, aucune autre décision n'est possible sur une mauvaise mission
        self.assertEqual(self.post("agentique:api_decider", run=99, ok=True).status_code, 409)
        e = self.post("agentique:api_decider", run=e["run"]["id"], ok=True).json()
        self.assertIsNone(e["attente"])
        self.assertIn("decision", types(e))
        self.assertIn("ticket n°4127", reponse(e))

    def test_refus_l_agent_s_adapte(self, _):
        e = self.post("agentique:api_lancer", mission="commande", autonomie="valider").json()
        e = self.post("agentique:api_decider", run=e["run"]["id"], ok=False).json()
        self.assertIn("non passée", reponse(e))
        self.assertNotIn("C-882", reponse(e))

    def test_une_mission_a_la_fois(self, _):
        self.post("agentique:api_lancer", mission="commande", autonomie="autonome")
        self.assertEqual(self.post("agentique:api_lancer", mission="vibration", autonomie="autonome").status_code, 409)

    def test_mission_en_attente_remplacable(self, _):
        e = self.post("agentique:api_lancer", mission="commande", autonomie="valider").json()
        self.assertIsNotNone(e["attente"])
        e2 = self.post("agentique:api_lancer", mission="vibration", autonomie="valider")
        self.assertEqual(e2.status_code, 200)
        self.assertEqual(e2.json()["run"]["mission"], "vibration")

    def test_parametres_invalides(self, _):
        for d in ({"mission": "x", "autonomie": "valider"}, {"mission": "commande", "autonomie": "x"}, {}):
            self.assertEqual(self.post("agentique:api_lancer", **d).status_code, 400, d)
        self.assertEqual(self.post("agentique:api_decider", run=1, ok="oui").status_code, 400)

    def test_serveurs_sans_surchauffe_pas_d_alerte(self, _):
        e = self.post("agentique:api_lancer", mission="serveurs", autonomie="valider").json()
        self.assertIsNone(e["attente"])
        self.assertIn("Tout va bien", reponse(e))
        self.assertIn("Pi 2 : 52\u00a0°C", json.dumps(e["run"]["evenements"], ensure_ascii=False))


class ServeursTests(TestCase):
    def setUp(self):
        moteur.reinitialiser()

    def lancer(self, temps, autonomie="valider"):
        with mock.patch("agentique.moteur.lire_temperatures", return_value=temps):
            return self.client.post(reverse("agentique:api_lancer"),
                                    json.dumps({"mission": "serveurs", "autonomie": autonomie}),
                                    content_type="application/json").json()

    def test_surchauffe_demande_validation(self):
        e = self.lancer({1: 45.0, 2: SEUIL_ALERTE_C + 3, 3: 40.0})
        self.assertIn("Pi 2", e["attente"]["action"])

    def test_capteurs_injoignables(self):
        e = self.lancer({1: None, 2: None, 3: None}, autonomie="autonome")
        self.assertIn("capteurs ne répondent pas", reponse(e))
        self.assertIn("auto", types(e))
