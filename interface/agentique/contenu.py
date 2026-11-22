"""
L'IA QUI AGIT — contenu éditable (hors scénarios)
=================================================

  - OUTILS    : les 4 outils dont dispose l'agent (affichés sur le schéma) ;
  - MISSIONS  : les missions proposées ; le déroulé de chacune est écrit dans
                scenarios.py (textes de réflexion, appels d'outils, réponse) ;
  - AUTONOMIES: les deux niveaux d'autonomie ;
  - PHASES    : les étapes de la boucle de l'agent ;
  - INFOS     : les textes des info-bulles du schéma.
"""

# Clé -> nom affiché et description courte (l'ordre est celui du schéma)
OUTILS = {
    "capteurs": {"nom": "Capteurs", "desc": "Mesures en direct des machines"},
    "doc": {"nom": "Documentation", "desc": "Notices, normes, catalogues"},
    "gmao": {"nom": "Logiciel de maintenance", "desc": "Historique, stock, planning"},
    "message": {"nom": "Messagerie", "desc": "Alertes, tickets, commandes"},
}

MISSIONS = [
    {
        "cle": "serveurs",
        "titre": "Surveiller les serveurs",
        "objectif": "Vérifie la température des 3 serveurs de la maquette et préviens le technicien si l’un d’eux surchauffe.",
    },
    {
        "cle": "vibration",
        "titre": "Une machine vibre",
        "objectif": "La presse n°3 vibre anormalement. Trouve la cause probable et organise l’intervention.",
    },
    {
        "cle": "commande",
        "titre": "Commander des pièces",
        "objectif": "Il ne reste presque plus de filtres pour le compresseur. Commande ce qu’il faut pour le mois prochain.",
    },
]

AUTONOMIES = {
    "valider": {"titre": "Demander avant d’agir", "desc": "Un humain valide chaque action"},
    "autonome": {"titre": "Agir seul", "desc": "Aucun contrôle humain"},
}

PHASES = {
    "comprendre": "Comprendre",
    "planifier": "Planifier",
    "agir": "Agir",
    "observer": "Observer",
    "repondre": "Répondre",
}

INFOS = {
    "vous": {"t": "Vous", "w": "Vous confiez une mission à l’agent, en langage courant. Il revient vers vous avec un résultat… ou une demande de validation."},
    "agent": {"t": "Agent IA", "w": "Un modèle de langage placé dans une boucle : il réfléchit, choisit un outil, lit le résultat, puis recommence jusqu’à atteindre l’objectif.",
              "r": "Sur la maquette, le raisonnement de l’agent est scénarisé ; les mesures des serveurs, elles, sont réelles."},
    "pensee": {"t": "Raisonnement", "w": "L’agent explique ce qu’il comprend et ce qu’il va faire. C’est du texte généré, comme une réponse de chatbot."},
    "plan": {"t": "Plan", "w": "L’agent découpe la mission en étapes, puis les coche au fur et à mesure. Il peut changer de plan selon ce qu’il observe."},
    "memoire": {"t": "Mémoire de travail", "w": "Ce que l’agent a appris grâce aux outils. Ces notes sont renvoyées au modèle à chaque tour de boucle."},
    "capteurs": {"t": "Outil : capteurs", "w": "Lit des mesures en direct. Pour les serveurs de la maquette, ce sont les vraies températures des Raspberry Pi."},
    "doc": {"t": "Outil : documentation", "w": "Recherche dans des notices, des normes ou des catalogues, comme un moteur de recherche interne."},
    "gmao": {"t": "Outil : logiciel de maintenance", "w": "GMAO : historique des pannes, stock de pièces, planning des techniciens, tickets d’intervention."},
    "message": {"t": "Outil : messagerie", "w": "Permet d’agir sur le monde réel : alerter, créer un ticket, passer une commande. D’où l’intérêt d’une validation humaine."},
    "garde": {"t": "Garde-fou", "w": "Avant une action qui engage l’entreprise, l’agent demande l’accord d’un humain. Sans ce garde-fou, une erreur de l’IA a des conséquences réelles."},
}
