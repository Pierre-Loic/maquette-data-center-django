"""
Déroulé des missions de l'agent.

Chaque mission est un générateur Python qui produit les étapes de l'agent :
    pense(...)      réflexion affichée dans la bulle de l'agent
    plan([...])     liste des étapes prévues
    etape(i, etat)  avancement d'une étape du plan ("encours", "fait", "annule")
    appel(...)      appel d'un outil (phase « Agir »)
    resultat(...)   réponse de l'outil + note ajoutée à la mémoire (« Observer »)
    valider(...)    action qui engage l'entreprise : `ok = yield valider(...)`
                    renvoie True si l'humain valide (ou si l'agent est autonome)
    repondre(...)   réponse finale à la personne

Les textes peuvent être modifiés librement. Le raisonnement est scénarisé ;
seule la mission « serveurs » utilise des mesures réelles (températures des
Raspberry Pi), et l'agent décide d'alerter ou non selon ces valeurs.
"""

SEUIL_ALERTE_C = 70


def _duree_lecture(texte: str) -> int:
    """Temps laissé pour lire un texte (ms)."""
    return max(2200, 900 + 38 * len(texte))


def pense(texte, phase="planifier"):
    return {"type": "think", "phase": phase, "text": texte, "d": _duree_lecture(texte)}


def plan(items):
    return {"type": "plan", "phase": "planifier", "items": items, "d": 2200}


def etape(index, etat):
    return {"type": "plan_step", "index": index, "etat": etat, "d": 400}


def appel(outil, texte):
    return {"type": "tool_call", "phase": "agir", "outil": outil, "text": texte, "d": 1700}


def resultat(outil, texte, note):
    return {"type": "tool_result", "phase": "observer", "outil": outil, "text": texte, "note": note,
            "d": _duree_lecture(texte)}


def valider(outil, action):
    return {"type": "validation", "phase": "agir", "outil": outil, "action": action, "d": 600}


def repondre(texte):
    return {"type": "answer", "phase": "repondre", "text": texte}


# --------------------------------------------------------------------------
# Mission 1 : surveiller les serveurs de la maquette (mesures réelles)
# --------------------------------------------------------------------------
def serveurs(temperatures):
    """temperatures : {numéro du Pi: °C ou None si la mesure a échoué}"""
    yield pense("Je dois mesurer la température des 3 serveurs, la comparer à un seuil, "
                "puis prévenir le technicien seulement si c’est nécessaire.", "comprendre")
    yield plan(["Lire les températures", "Trouver le seuil d’alerte", "Comparer", "Prévenir si besoin"])

    yield etape(0, "encours")
    yield appel("capteurs", "lire_temperatures(rack=\"maquette\")")
    mesures = {pi: t for pi, t in temperatures.items() if t is not None}
    if not mesures:
        yield resultat("capteurs", "Aucune réponse des capteurs.", "Capteurs injoignables")
        yield etape(0, "annule")
        yield pense("Sans mesure, je ne peux pas conclure. Je préviens le technicien "
                    "que les capteurs ne répondent plus.")
        ok = yield valider("message", "Envoyer une alerte : « Capteurs de la maquette injoignables »")
        if ok:
            yield appel("message", "envoyer_alerte(technicien, \"Capteurs injoignables\")")
            yield resultat("message", "Alerte envoyée.", "Technicien prévenu")
            yield repondre("Je n’ai pas pu lire les températures : les capteurs ne répondent pas. "
                           "J’ai prévenu le technicien.")
        else:
            yield repondre("Je n’ai pas pu lire les températures : les capteurs ne répondent pas. "
                           "Comme demandé, je n’ai prévenu personne.")
        return

    texte = " · ".join(f"Pi {pi} : {t:.0f} °C" for pi, t in sorted(mesures.items()))
    yield resultat("capteurs", texte, texte)
    yield etape(0, "fait")

    yield etape(1, "encours")
    yield appel("doc", "chercher(\"température maximale Raspberry Pi\")")
    yield resultat("doc", f"Le processeur ralentit vers 80 °C. Alerte conseillée dès {SEUIL_ALERTE_C} °C.",
                   f"Seuil d’alerte : {SEUIL_ALERTE_C} °C")
    yield etape(1, "fait")

    yield etape(2, "encours")
    chauds = {pi: t for pi, t in mesures.items() if t >= SEUIL_ALERTE_C}
    pi_max, t_max = max(mesures.items(), key=lambda x: x[1])
    if not chauds:
        yield pense(f"La plus haute température est {t_max:.0f} °C (Pi {pi_max}), sous le seuil de "
                    f"{SEUIL_ALERTE_C} °C. Inutile de déranger le technicien.")
        yield etape(2, "fait")
        yield etape(3, "annule")
        yield repondre(f"Tout va bien : les 3 serveurs sont sous {SEUIL_ALERTE_C} °C "
                       f"(maximum {t_max:.0f} °C sur le Pi {pi_max}). Je n’ai envoyé aucune alerte.")
        return

    liste = ", ".join(f"Pi {pi}" for pi in sorted(chauds))
    yield pense(f"{liste} dépasse{'nt' if len(chauds) > 1 else ''} {SEUIL_ALERTE_C} °C. "
                "Il faut prévenir le technicien avant que le processeur ralentisse.")
    yield etape(2, "fait")
    yield etape(3, "encours")
    ok = yield valider("message", f"Envoyer une alerte : « Surchauffe sur {liste} »")
    if ok:
        yield appel("message", f"envoyer_alerte(technicien, \"Surchauffe {liste}\")")
        yield resultat("message", "Alerte envoyée au technicien.", "Technicien prévenu")
        yield etape(3, "fait")
        yield repondre(f"Attention : {liste} surchauffe ({t_max:.0f} °C au maximum). "
                       "J’ai prévenu le technicien.")
    else:
        yield etape(3, "annule")
        yield pense("Alerte refusée : je n’envoie rien, mais je signale le problème dans ma réponse.")
        yield repondre(f"{liste} dépasse {SEUIL_ALERTE_C} °C ({t_max:.0f} °C au maximum). "
                       "Comme demandé, je n’ai pas envoyé d’alerte : à surveiller.")


# --------------------------------------------------------------------------
# Mission 2 : une machine vibre
# --------------------------------------------------------------------------
def vibration():
    yield pense("La presse n°3 vibre : je dois trouver la cause probable, "
                "puis organiser une intervention avant la panne.", "comprendre")
    yield plan(["Mesurer la vibration", "Consulter l’historique", "Chercher la cause", "Planifier l’intervention"])

    yield etape(0, "encours")
    yield appel("capteurs", "lire_capteurs(machine=\"presse 3\")")
    yield resultat("capteurs", "Vibration : 7,8 mm/s (normale < 4,5) · Palier : 68 °C",
                   "Vibration ×1,7 · palier chaud")
    yield etape(0, "fait")

    yield etape(1, "encours")
    yield appel("gmao", "historique(machine=\"presse 3\")")
    yield resultat("gmao", "Roulement changé il y a 14 mois. Durée de vie conseillée : 12 mois.",
                   "Roulement de 14 mois (usé ?)")
    yield etape(1, "fait")

    yield etape(2, "encours")
    yield appel("doc", "chercher(\"vibration forte + palier chaud\")")
    yield resultat("doc", "Vibration élevée et palier chaud : usure du roulement probable.",
                   "Cause probable : roulement")
    yield etape(2, "fait")
    yield pense("Trois indices concordent : la cause probable est un roulement usé. "
                "Je cherche un créneau pour le remplacer.")

    yield etape(3, "encours")
    yield appel("gmao", "planning(equipe=\"maintenance\")")
    yield resultat("gmao", "Un technicien est disponible demain à 8 h.", "Créneau : demain 8 h")
    ok = yield valider("message", "Créer un ticket : remplacer le roulement de la presse 3, demain à 8 h")
    if ok:
        yield appel("message", "creer_ticket(\"presse 3\", \"remplacer roulement\", \"demain 8 h\")")
        yield resultat("message", "Ticket n°4127 créé.", "Ticket n°4127")
        yield etape(3, "fait")
        yield repondre("Cause probable : roulement usé (vibration 7,8 mm/s, palier à 68 °C, roulement de 14 mois). "
                       "Remplacement planifié demain à 8 h, ticket n°4127.")
    else:
        yield etape(3, "annule")
        yield pense("L’intervention n’est pas validée. Je donne mon diagnostic sans rien planifier.")
        yield repondre("Cause probable : roulement usé (vibration 7,8 mm/s, palier à 68 °C, roulement de 14 mois). "
                       "Aucune intervention planifiée : à décider par l’équipe.")


# --------------------------------------------------------------------------
# Mission 3 : commander des pièces
# --------------------------------------------------------------------------
def commande():
    yield pense("Je dois éviter de manquer de filtres le mois prochain : "
                "vérifier le stock, calculer la quantité, choisir un fournisseur, commander.", "comprendre")
    yield plan(["Vérifier le stock", "Calculer la quantité", "Comparer les fournisseurs", "Passer commande"])

    yield etape(0, "encours")
    yield appel("gmao", "stock(piece=\"filtre compresseur\")")
    yield resultat("gmao", "En stock : 2 filtres. Consommation : 6 par mois.", "Stock 2 · besoin 6/mois")
    yield etape(0, "fait")

    yield etape(1, "encours")
    yield pense("Il manque 6 − 2 = 4 filtres pour le mois. J’en ajoute 2 par sécurité : 6 filtres à commander.")
    yield etape(1, "fait")

    yield etape(2, "encours")
    yield appel("doc", "catalogue(piece=\"filtre compresseur\")")
    yield resultat("doc", "Fournisseur A : 38 € · livré en 2 jours. Fournisseur B : 31 € · livré en 10 jours.",
                   "A : 38 €, 2 j · B : 31 €, 10 j")
    yield pense("B est moins cher, mais avec 2 filtres en stock nous serions à court avant sa livraison. "
                "Je choisis A.")
    yield etape(2, "fait")

    yield etape(3, "encours")
    ok = yield valider("message", "Commander 6 filtres au fournisseur A pour 228 €")
    if ok:
        yield appel("message", "commander(fournisseur=\"A\", piece=\"filtre\", quantite=6)")
        yield resultat("message", "Commande n°C-882 envoyée. Livraison dans 2 jours.", "Commande n°C-882")
        yield etape(3, "fait")
        yield repondre("J’ai commandé 6 filtres au fournisseur A (228 €), livrés dans 2 jours : "
                       "le fournisseur B était moins cher mais trop lent.")
    else:
        yield etape(3, "annule")
        yield pense("Commande refusée : je ne passe pas la commande et je résume ma proposition.")
        yield repondre("Je propose de commander 6 filtres au fournisseur A (228 €, livrés en 2 jours). "
                       "Commande non passée : elle attend votre décision.")


SCENARIOS = {"serveurs": serveurs, "vibration": vibration, "commande": commande}
