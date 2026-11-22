"""
L'IA CONSOMME COMBIEN ? — contenu éditable
==========================================

Tout ce qui s'affiche se règle ici :
  - QUESTIONS : les prompts proposés (titre court affiché + prompt envoyé) ;
  - MODELES   : les modèles proposés et leur nom exact dans Ollama
                (doivent être installés sur les 3 Raspberry Pi) ;
  - LONGUEURS : la longueur de réponse demandée (consigne ajoutée au prompt) ;
  - les valeurs utilisées pour les calculs d'énergie et de CO₂.
"""

from dashboard.views import POWER_WATTS

QUESTIONS = [
    {"titre": "Les réseaux de neurones",
     "prompt": "Qu’est-ce qu’un réseau de neurones artificiels ?"},
    {"titre": "L’IA à l’usine",
     "prompt": "Comment l’IA peut-elle aider à la maintenance prédictive dans une usine ?"},
    {"titre": "L’énergie de l’IA",
     "prompt": "Pourquoi l’IA générative consomme-t-elle autant d’énergie ?"},
    {"titre": "Les hallucinations",
     "prompt": "Qu’est-ce qu’une hallucination d’une IA générative ?"},
    {"titre": "La vision par ordinateur",
     "prompt": "Comment une IA repère-t-elle un défaut sur une pièce grâce à une caméra ?"},
]

MODELES = {
    "Gemma": {"desc": "Google · petit", "ollama": "gemma3:270m"},
    "Falcon": {"desc": "TII · moyen", "ollama": "falcon3:1b"},
    "Ministral": {"desc": "Mistral AI · grand", "ollama": "ministral-3:3b"},
}

LONGUEURS = {
    "courte": {"titre": "Courte", "consigne": "Réponds en 1 à 2 phrases maximum."},
    "moyenne": {"titre": "Moyenne", "consigne": "Réponds en un paragraphe d’environ 5 phrases."},
    "longue": {"titre": "Longue", "consigne": "Réponds en détail en au moins 3 paragraphes."},
}

# ---- Valeurs utilisées pour les calculs (mêmes que pour la Fête de la science) ----
CALCULS = {
    # Puissance supposée constante d'un Raspberry Pi pendant la génération (W)
    "puissance_pi_w": POWER_WATTS,
    # Énergie d'inférence de ChatGPT : Wh pour 100 tokens générés (estimation)
    "gpt_wh_100_tokens": 0.728,
    # Électricité en France : gCO₂eq par kWh (ADEME, Base Empreinte)
    "co2_g_par_kwh": 41.44,
    # Usage annuel : prompts par jour × jours
    "prompts_par_jour": 50,
    "jours_par_an": 365,
}

# Durée de mesure de la température après la fin de la génération (s) : le Pi
# continue de chauffer quelques secondes après avoir terminé.
MESURE_APRES_S = 10
