import json

from django.test import TestCase
from django.urls import reverse

from .models import FriseScore


class FriseApiTests(TestCase):
    def post(self, **data):
        return self.client.post(reverse("histoire:api_score"), json.dumps(data), content_type="application/json")

    def test_page(self):
        self.assertEqual(self.client.get(reverse("histoire:index")).status_code, 200)

    def test_enregistre_et_classe(self):
        self.post(theme="tech", ms=90_000, erreurs=1, pseudo="Alice")
        r = self.post(theme="tech", ms=60_000, erreurs=0, pseudo="  Bob   L ").json()
        self.assertEqual(r["rang"], 1)
        self.assertEqual(r["total"], 2)
        self.assertEqual(r["score"]["pseudo"], "Bob L")
        self.assertEqual([e["pseudo"] for e in r["classements"]["tech"]], ["Bob L", "Alice"])
        self.assertEqual(r["classements"]["biz"], [])

    def test_egalite_departagee_par_erreurs_puis_anciennete(self):
        self.post(theme="env", ms=50_000, erreurs=2, pseudo="A")
        self.post(theme="env", ms=50_000, erreurs=0, pseudo="B")
        r = self.post(theme="env", ms=50_000, erreurs=0, pseudo="C").json()
        self.assertEqual(r["rang"], 2)
        self.assertEqual([e["pseudo"] for e in r["classements"]["env"]], ["B", "C", "A"])

    def test_pseudo_par_defaut(self):
        self.assertEqual(self.post(theme="bia", ms=1000, pseudo="   ").json()["score"]["pseudo"], "Anonyme")

    def test_donnees_invalides(self):
        for data in ({"theme": "xx", "ms": 1000}, {"theme": "tech", "ms": 0},
                     {"theme": "tech", "ms": 240_001}, {"theme": "tech", "ms": "abc"}, {"ms": 1000}):
            self.assertEqual(self.post(**data).status_code, 400, data)
        self.assertFalse(FriseScore.objects.exists())

    def test_classement_get(self):
        self.post(theme="biz", ms=1000, pseudo="Z")
        r = self.client.get(reverse("histoire:api_classement")).json()
        self.assertEqual(r["classements"]["biz"][0]["pseudo"], "Z")
