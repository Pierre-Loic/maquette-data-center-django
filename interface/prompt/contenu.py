"""
LA VIE D'UN PROMPT — contenu éditable
=====================================

Tout ce qui s'affiche sur les deux écrans se règle ici :
  - QUESTIONS : les questions proposées et leur réponse simulée, découpée en
    tokens (garder l'espace en début de token quand il y en a un) ;
    la réponse simulée ne sert qu'en mode démo (Raspberry Pi simulés) ;
  - PRE_PROMPT: consignes ajoutées avant la question envoyée au vrai Pi ;
  - MODELES   : les modèles proposés, leur nom dans Ollama (doit être
    installé sur les 3 Pi) et leurs valeurs simulées pour le mode démo ;
  - PIS       : les Raspberry Pi du mini rack ;
  - PHASES    : le nom des 5 étapes ;
  - NARRATION : les phrases du bandeau « Ce qui se passe » ({...} est remplacé
                par les vraies mesures) ;
  - INFOS     : les textes des info-bulles de l'écran d'observation
                (t = titre, w = à quoi ça sert, m = sur la maquette,
                 r = en vrai, l = limite, facultatif).
"""

QUESTIONS = [
    {
        "q": "L’IA peut-elle se tromper ?",
        "a": ["Oui", ",", " une", " IA", " générative", " peut", " inventer", " des", " faits", " qui",
              " semblent", " vrais", " :", " on", " parle", " d’", "hallucinations", "."],
    },
    {
        "q": "C’est quoi un data center ?",
        "a": ["Un", " data", " center", " est", " un", " bâtiment", " rempli", " de", " serveurs", " qui",
              " stockent", " et", " traitent", " des", " données", "."],
    },
    {
        "q": "Comment fonctionne une IA générative ?",
        "a": ["Elle", " apprend", " sur", " d’", "énormes", " quantités", " de", " textes", ",", " puis",
              " devine", " le", " mot", " suivant", ",", " un", " token", " à", " la", " fois", "."],
    },
    {
        "q": "Pourquoi refroidir les serveurs ?",
        "a": ["Les", " processeurs", " transforment", " presque", " toute", " l’", "électricité", " en", " chaleur",
              ",", " qu’", "il", " faut", " évacuer", " pour", " éviter", " la", " surchauffe", "."],
    },
]

# Consignes ajoutées avant la question (vrais Pi) : réponse très courte, pour
# qu'elle s'affiche vite et tienne dans le schéma.
PRE_PROMPT = (
    "Tu es un assistant pédagogique sur un salon professionnel. "
    "Réponds en français, en une seule phrase très courte de 15 mots maximum, "
    "sans liste ni mise en forme."
)

# ollama = nom exact du modèle dans Ollama sur les Raspberry Pi.
# fournisseur = entreprise qui a créé le modèle.
# preprompt_cache = tokens du pré-prompt caché que le modèle ajoute lui-même
#   (mesuré sur les Pi : Ministral ajoute ~550 tokens de consignes de Mistral AI,
#    Gemma et Falcon seulement quelques balises de mise en forme).
# Valeurs simulées (mode démo uniquement), mesurées sur les vrais Pi de la maquette :
# ram = part de la RAM occupée (%), load = durée de chargement (ms),
# lecture = vitesse de lecture du prompt hors cache (tokens/s),
# ecriture = vitesse de génération (tokens/s)
MODELES = {
    "Gemma": {"desc": "Google · petit", "ollama": "gemma3:270m", "fournisseur": "Google", "preprompt_cache": 0,
              "ram": 8, "load": 2700, "lecture": 330, "ecriture": 27},
    "Falcon": {"desc": "TII · moyen", "ollama": "falcon3:1b", "fournisseur": "TII", "preprompt_cache": 0,
               "ram": 16, "load": 24600, "lecture": 34, "ecriture": 5.4},
    "Ministral": {"desc": "Mistral AI · grand", "ollama": "ministral-3:3b", "fournisseur": "Mistral AI", "preprompt_cache": 552,
                  "ram": 26, "load": 10000, "lecture": 19, "ecriture": 3.2},
}

# Température de repos simulée de chaque Pi (°C)
PIS = {1: 43, 2: 46, 3: 41}

# RAM occupée par le système, hors modèle (%)
RAM_BASE = 3

PHASES = ["Envoi", "Découpage en tokens", "Chargement du modèle", "Lecture du prompt", "Génération des tokens"]

NARRATION = {
    "envoi": "Votre question part vers le data center, accompagnée du pré-prompt.",
    "decoupage": "Le texte est découpé en tokens : des morceaux de mots, la seule chose que le modèle sait lire.",
    "preprompt_cache": "{fournisseur} ajoute en plus son propre pré-prompt, invisible pour vous : {n} tokens de plus à lire !",
    "chargement": "Le modèle {modele} est copié de la mémoire flash vers la RAM…",
    "charge": "Modèle chargé en RAM en {duree}.",
    "deja_charge": "Le modèle {modele} est déjà en RAM : pas besoin de le recharger.",
    "lecture": "Lecture du prompt : le processeur traite les quelque {n} tokens du prompt tous en même temps.",
    "generation": "Lecture faite en {duree}. Le modèle écrit maintenant la réponse un token à la fois : chaque token dépend des précédents.",
    "generation_sans_duree": "Le modèle écrit la réponse un token à la fois : chaque token dépend des précédents.",
    "fin": "Lire : {v_lecture} tokens/s · Écrire : {v_ecriture} tokens/s → écrire est {ratio}× plus lent que lire.",
    "fin_cache": "Le début du prompt était déjà en mémoire (cache) : {relus}. Écrire : {v_ecriture} tokens/s.",
    "fin_sans_detail": "Réponse terminée en {duree}.",
}

INFOS = {
    "c0": {"t": "Pré-prompt", "w": "Consignes du système ajoutées avant votre question (rôle, règles, ton).",
           "m": "Texte fixe ajouté par Django. Ministral y ajoute en plus le pré-prompt caché de Mistral AI (~550 tokens).",
           "r": "Souvent ajouté côté fournisseur, invisible pour l’utilisateur… mais il faut quand même le lire !"},
    "c1": {"t": "Historique", "w": "Les échanges précédents, renvoyés à chaque message.",
           "m": "Gardé par Django pendant la session.", "r": "Sans lui, le modèle ne sait pas ce qui vient d’être dit."},
    "c2": {"t": "Mémoire", "w": "Informations retenues d’une conversation à l’autre.",
           "m": "Simulée : aucune donnée personnelle conservée.", "r": "Résumés de préférences ajoutés au contexte."},
    "c3": {"t": "Prompt", "w": "La question choisie.",
           "m": "Envoyée par Django au Raspberry Pi sélectionné.", "r": "Souvent la plus petite partie du paquet envoyé."},
    "screen": {"t": "Ordinateur de l’utilisateur", "w": "Là où la question part et où la réponse s’affiche.",
               "m": "Un navigateur et un serveur Django local, qui fait les appels d’API.",
               "r": "Votre ordinateur ou votre téléphone."},
    "net": {"t": "Réseau (câble RJ45)", "w": "Transporte la requête, puis les tokens en sens inverse.",
            "m": "Un câble Ethernet RJ45 relie l’ordinateur au mini rack.",
            "r": "Internet : routeurs, fibres, liaisons longue distance."},
    "rack": {"t": "Maquette de data center", "w": "Là où tourne le modèle.",
             "m": "Mini rack de 3 Raspberry Pi avec FastAPI et Ollama.",
             "r": "Des salles de serveurs, avec forte alimentation et refroidissement."},
    "entry": {"t": "Entrée (FastAPI)", "w": "Reçoit la requête, la contrôle, la transmet au modèle.",
              "m": "Une API FastAPI sur le Raspberry Pi choisi.",
              "r": "Répartiteurs de charge, files d’attente, filtres de sécurité."},
    "flash": {"t": "Mémoire flash", "w": "Stockage durable du fichier du modèle choisi.",
              "m": "Carte SD ou SSD du Pi (à confirmer).", "r": "Disques rapides, sollicités surtout au déploiement."},
    "ram": {"t": "RAM", "w": "Le modèle doit y tenir en entier pour calculer vite. Le pourcentage montre la part de RAM occupée.",
            "m": "RAM du Pi choisi, mesurée en direct (simulée en mode démo). Changer de modèle oblige à le recharger.",
            "r": "Mémoire des GPU, bien plus rapide.", "l": "Limite : débit flash → RAM au chargement"},
    "cpu": {"t": "CPU", "w": "Fabrique la réponse, token après token. Il chauffe et monte en fréquence quand il travaille.",
            "m": "CPU du Pi choisi : température, fréquence et utilisation mesurées en direct (simulées en mode démo).",
            "r": "GPU ou accélérateurs spécialisés, très gourmands et très chauds.", "l": "Limite : puissance de calcul du CPU"},
    "tokens": {"t": "Tokens", "w": "Morceaux de mots : le modèle ne lit et n’écrit que ça. Violet : le prompt lu ; rouge : la réponse écrite.",
               "m": "Découpage simplifié pour l’affichage ; les nombres de tokens et les durées viennent du Pi.",
               "r": "Les services limitent et facturent selon les tokens."},
    "p0": {"t": "1 · Envoi", "w": "La question part avec pré-prompt, historique et mémoire, à chaque message.",
           "m": "Django assemble le paquet et appelle l’API du Pi.", "r": "Envoi par Internet vers le service."},
    "p1": {"t": "2 · Découpage en tokens", "w": "Le texte (pré-prompt + question) est découpé en tokens, des morceaux de mots.",
           "m": "Ollama découpe le prompt sur le Pi. Une requête à la fois.",
           "r": "Un répartiteur choisit d’abord un serveur libre, parfois après une file d’attente."},
    "p2": {"t": "3 · Chargement du modèle", "w": "Les poids du modèle passent de la mémoire flash à la RAM. Sauté s’ils y sont déjà.",
           "m": "Le Pi garde un modèle en RAM pendant 30 min. Durée mesurée sur le Pi.",
           "r": "Modèles chargés en permanence dans la mémoire des accélérateurs.",
           "l": "Limite : débit de transfert flash → RAM"},
    "p3": {"t": "4 · Lecture du prompt (prefill)", "w": "Le modèle lit tous les tokens du prompt en même temps, en parallèle : c’est rapide.",
           "m": "Durée et nombre de tokens mesurés par Ollama sur le Pi.",
           "r": "Les GPU lisent des prompts de milliers de tokens en une fraction de seconde."},
    "p4": {"t": "5 · Génération des tokens (decode)", "w": "Le modèle écrit la réponse un token à la fois : chaque token dépend de tous les précédents, impossible de paralléliser. C’est l’étape la plus lente.",
           "m": "Chaque token est envoyé vers l’écran dès qu’il est calculé (streaming). Débit mesuré sur le Pi.",
           "r": "Même principe, d’où l’effet « quelqu’un écrit en direct ».",
           "l": "Limite : puissance de calcul du CPU et débit de la RAM"},
}
