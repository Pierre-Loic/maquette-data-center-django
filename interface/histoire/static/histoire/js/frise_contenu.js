/* =====================================================================
   LA FRISE DE L'IA — CONTENU ÉDITABLE (version stand SEPEM)
   ---------------------------------------------------------------------
   Tout ce qui s'affiche se règle dans les 4 blocs ci-dessous :
     1. REGLAGES  : nombre de cartes, durée, pénalité, décompte
     2. TEXTES    : tous les textes des écrans (choix du thème, jeu, résultats)
     3. THEMES    : les thématiques (nom, description, couleurs)
     4. CARTES    : le contenu des cartes (une carte = un bloc { ... })

   Règles à respecter :
     - Garder les guillemets "..." et les virgules en fin de ligne.
     - Dans les textes, {n}, {titre}, {temps}... sont remplacés par le jeu :
       ne pas les supprimer.
     - Pour AJOUTER une carte : copier un bloc de CARTES, le coller dans la
       bonne thématique et changer son contenu. L'idéal est 10 à 12 cartes par
       thématique, avec au moins 6 années différentes (le jeu tire 6 cartes
       d'années toutes différentes).
     - Le champ "theme" doit valoir une des clés de THEMES : biz, tech, bia, env.
       ⚠ Ajouter ou renommer une thématique : mettre aussi à jour THEMES dans
       histoire/models.py (le serveur refuse les scores d'un thème inconnu).
     - Changer dureeSecondes : mettre aussi à jour DUREE_MAX_MS dans
       histoire/models.py.
   ===================================================================== */

/* ---------- 1. REGLAGES ---------- */
const REGLAGES = {
  nbCartes: 6,            // cartes tirées à chaque partie
  dureeSecondes: 240,     // durée maximale : 240 = 4 minutes
  penaliteSecondes: 30,   // pénalité par erreur
  decompte: 3,            // décompte avant le début (secondes)
};

/* ---------- 2. TEXTES (écrans, boutons, messages) ---------- */
const TEXTES = {

  /* Général */
  formatDuree: "{m} min {s} s",

  /* Écran 1 : choix de la thématique */
  accueilAccroche: "Remettez l’histoire de l’IA dans l’ordre !",
  accueilRegles: ["{n} cartes", "{minutes} minutes", "+{penalite} s par erreur"],
  selectionTitre: "Choisissez un thème",
  selectionRecord: "Record : {temps} · {nom}",
  selectionSansRecord: "Pas encore de record",

  /* Écran 2 : le jeu */
  decompteTitre: "Préparez-vous…",
  jeuRegion: "Partie en cours",
  jeuTempsRestant: "Temps restant",
  jeuErreurs: "Erreurs",
  jeuPlacees: "Placées",
  jeuAbandonner: "Abandonner",
  jeuTitreMain: "Vos cartes",
  jeuAide: "Glissez chaque carte sur sa date",
  jeuAideSelection: "Cliquez maintenant sur la bonne date",
  jeuAideFin: "Toutes les cartes sont placées !",
  jeuTitreFrise: "La frise",
  jeuLireVerso: "En savoir plus",
  jeuDeposer: "Déposez ici",
  jeuPenaliteFlash: "+{n} s",
  versoDateInconnue: "????",
  versoDateAria: "Date à trouver",
  fermer: "Fermer",

  /* Écran 3 : résultats et classement */
  resTitreVictoire: "Bravo, frise complète !",
  resTitreDefaite: "Temps écoulé !",
  resDetailSansErreur: "Sans aucune erreur !",
  resDetailErreurs: "dont {pen} s de pénalité ({n} erreur(s))",
  resScoreDefaite: "{ok} cartes placées sur {n}",
  resDetailDefaite: "Retentez votre chance !",
  resPseudo: "Votre pseudo",
  pseudoDefaut: "Anonyme",
  resEnregistrer: "Enregistrer mon score",
  resEnregistre: "Bravo {nom} : {rang}e sur {total} !",
  resEnregistrePremier: "Bravo {nom} : nouveau record !",
  resErreurEnregistrement: "Le score n’a pas pu être enregistré.",
  resClassement: "Classement",
  classementErreurs: "{n} err.",
  classementVide: "Aucun score pour l’instant : soyez le premier !",
  resRejouer: "Rejouer",
  resAutre: "Changer de thème",
  resCartes: "Les cartes de la partie",

  /* Crédits (licence CC BY-NC : à conserver) */
  piedCredit: "Jeu conçu dans le cadre de la chaire AugmentIA et du MIAI Cluster.",
  piedAuteurs: "Auteurs du jeu d’origine : Didier Schwab, Diandra Fabre, Grégory Rojas, Anne-Lise Boute. Licence CC BY-NC 4.0.",

  /* Annonces pour lecteurs d’écran et libellés d’accessibilité */
  annonceDepart: "C’est parti ! Vous avez {minutes} minutes.",
  annonceReste: "Il reste {temps}",
  annonceChoisir: "Choisissez d’abord une carte.",
  annonceBonne: "Bonne date : {annee}.",
  annonceMauvaise: "Mauvaise date. Pénalité de {n} secondes.",
  annonceVictoire: "Bravo ! Temps : {temps}",
  ariaCarte: "Carte : {titre}, {theme}",
  ariaLireVerso: "En savoir plus : {titre}",
  ariaDeposer: "Déposer la carte sélectionnée sur la date {annee}",
};

/* ---------- 3. THEMES ---------- */
const THEMES = {
  biz: {
    nom: "Modèle d’affaire",
    description: "Rachats, levées de fonds, alliances et procès : comment l’IA est devenue une industrie.",
    couleurFond: "#F6E0C9",   // fond des cartes
    couleurTexte: "#8A4108",  // titres et étiquettes
  },
  tech: {
    nom: "Technique",
    description: "Des premières machines à calculer aux réseaux de neurones et aux Transformers.",
    couleurFond: "#D9E6F2",   // fond des cartes
    couleurTexte: "#1D4E89",  // titres et étiquettes
  },
  bia: {
    nom: "Biais",
    description: "Quand les algorithmes reproduisent ou amplifient les discriminations.",
    couleurFond: "#CFEBE6",   // fond des cartes
    couleurTexte: "#0E6460",  // titres et étiquettes
  },
  env: {
    nom: "Environnement",
    description: "Énergie, carbone, eau, déchets : l’empreinte de l’IA.",
    couleurFond: "#DCEAD0",   // fond des cartes
    couleurTexte: "#3B6A1E",  // titres et étiquettes
  },
};

/* ---------- 4. CARTES ---------- */
const CARTES = [

  /* ===== MODÈLE D’AFFAIRE ===== */
  {
    theme: "biz",
    annee: 2005,
    lieu: "Seattle, novembre",
    titre: "Amazon lance Mechanical Turk",
    texte: "Amazon ouvre une place de marché où des entreprises confient à des milliers de personnes, les « turkers », de petites tâches que les machines font mal : étiqueter des images, transcrire, trier. Payées souvent quelques centimes l’unité, ces tâches fournissent les données qui nourrissent les IA. Le nom fait référence au « Turc mécanique » de 1770, faux automate où se cachait un joueur d’échecs.",
  },
  {
    theme: "biz",
    annee: 2014,
    lieu: "Londres, janvier",
    titre: "Google rachète DeepMind",
    texte: "Fondée à Londres en 2010 par Demis Hassabis, Shane Legg et Mustafa Suleyman, DeepMind n’a presque aucun produit, mais des chercheurs d’exception. Google l’acquiert pour une somme que la presse situe au-delà de 500 millions de dollars. Les grandes entreprises du numérique se mettent à acheter des laboratoires d’IA, parfois avant même qu’ils aient un produit.",
  },
  {
    theme: "biz",
    annee: 2015,
    lieu: "San Francisco, décembre",
    titre: "Création d’OpenAI",
    texte: "OpenAI est annoncée comme une organisation de recherche à but non lucratif, portée par Sam Altman, Elon Musk, Greg Brockman, Ilya Sutskever et d’autres, avec plus d’un milliard de dollars d’engagements. Sa mission : développer une IA qui profite à toute l’humanité. L’entreprise changera de structure en 2019 pour pouvoir lever des fonds bien plus importants.",
  },
  {
    theme: "biz",
    annee: 2019,
    lieu: "Seattle, 22 juillet",
    titre: "Microsoft mise un milliard sur OpenAI",
    texte: "Quelques mois après la création d’une branche à profits plafonnés, OpenAI annonce un investissement de 1 milliard de dollars de Microsoft. Le partenariat prévoit que la puissance de calcul d’OpenAI tourne sur le cloud Azure et que Microsoft devienne son partenaire privilégié. Il sera étendu à plusieurs reprises, avec de nouveaux milliards.",
  },
  {
    theme: "biz",
    annee: 2020,
    lieu: "OpenAI, juin",
    titre: "GPT-3 : l’IA vendue sur abonnement",
    texte: "OpenAI ne publie pas GPT-3 : elle l’ouvre en juin 2020 via une interface de programmation payante, une API, qui permet à des entreprises d’intégrer le modèle à leurs produits. En septembre, Microsoft obtient une licence exclusive sur le modèle lui-même. Le modèle « à l’usage » devient l’un des grands modèles d’affaires de l’IA.",
  },
  {
    theme: "biz",
    annee: 2021,
    lieu: "GitHub, juin",
    titre: "GitHub Copilot, l’assistant de code",
    texte: "GitHub, propriété de Microsoft, lance en préversion Copilot, un assistant qui complète le code des développeurs, basé sur un modèle d’OpenAI entraîné notamment sur du code public. Devenu payant en 2022, il est l’un des premiers produits d’IA générative vendus par abonnement à des millions de professionnels. Il déclenche aussi des débats juridiques sur les licences du code utilisé.",
  },
  {
    theme: "biz",
    annee: 2023,
    lieu: "Paris, juin",
    titre: "Mistral AI lève 105 millions d’euros",
    texte: "Fondée en avril 2023 par Arthur Mensch, Guillaume Lample et Timothée Lacroix, Mistral AI obtient, quatre semaines après sa création, 105 millions d’euros d’amorçage : un record européen pour une jeune pousse. L’entreprise promet des modèles ouverts et performants, pour que l’Europe ne dépende pas uniquement des acteurs américains.",
  },
  {
    theme: "biz",
    annee: 2023,
    lieu: "New York, 27 décembre",
    titre: "Le New York Times attaque OpenAI et Microsoft",
    texte: "Le quotidien saisit la justice américaine : il reproche aux deux entreprises d’avoir copié des millions de ses articles pour entraîner leurs modèles sans autorisation ni paiement, et réclame des dommages. Le procès ouvre un front juridique : les contenus des médias, des auteurs et des artistes doivent-ils être rémunérés quand ils servent à entraîner les IA ?",
  },
  {
    theme: "biz",
    annee: 2024,
    lieu: "Californie, février",
    titre: "Reddit vend ses données à Google",
    texte: "Reddit signe avec Google un accord qui donne accès à ses échanges pour entraîner des IA ; selon la presse, il rapporterait environ 60 millions de dollars par an. Après les médias et les éditeurs, les plateformes de discussion découvrent que leurs données sont devenues une ressource à vendre, alors que ce sont leurs utilisateurs qui les ont écrites.",
  },
  {
    theme: "biz",
    annee: 2024,
    lieu: "Wall Street, 18 juin",
    titre: "Nvidia, entreprise la plus valorisée du monde",
    texte: "Fabricant des puces graphiques indispensables à l’entraînement des IA, Nvidia dépasse 3 000 milliards de dollars de capitalisation et devient, le 18 juin, la première entreprise cotée du monde. Pendant la ruée vers l’or de l’IA, ce sont ceux qui vendent les pelles qui s’enrichissent : le matériel de calcul est le goulot d’étranglement de toute l’industrie.",
  },
  {
    theme: "biz",
    annee: 2025,
    lieu: "États-Unis, 21 janvier",
    titre: "Stargate : 500 milliards de dollars pour l’IA",
    texte: "À la Maison-Blanche, OpenAI, SoftBank et Oracle annoncent Stargate, un projet d’infrastructures d’IA (centres de données) dont l’enveloppe pourrait atteindre 500 milliards de dollars en quatre ans, dont 100 milliards engagés immédiatement. Jamais l’IA n’avait attiré des investissements d’une telle ampleur, ce qui relance les questions d’énergie et de rentabilité.",
  },
  {
    theme: "biz",
    annee: 2025,
    lieu: "Californie, septembre",
    titre: "Anthropic accepte de payer 1,5 milliard de dollars aux auteurs",
    texte: "Des écrivains avaient reproché à Anthropic d’avoir utilisé, pour entraîner ses modèles, des livres téléchargés depuis des bibliothèques pirates. L’entreprise accepte un accord de 1,5 milliard de dollars, soit environ 3 000 dollars par livre pour quelque 500 000 ouvrages : l’un des plus importants règlements de droit d’auteur de l’histoire américaine, qui crée un précédent pour toute l’industrie.",
  },

  /* ===== TECHNIQUE ===== */
  {
    theme: "tech",
    annee: 1642,
    lieu: "Rouen",
    titre: "La Pascaline",
    texte: "Pour aider son père, chargé de lever l’impôt en Normandie, le jeune Pascal conçoit une machine à roues dentées qui fait additions et soustractions. C’est l’une des toutes premières calculatrices : une opération de l’esprit est confiée à un mécanisme. Pascal écrira que sa machine « fait des effets qui approchent plus de la pensée que tout ce que font les animaux »… sans pour autant avoir de volonté.",
  },
  {
    theme: "tech",
    annee: 1943,
    lieu: "Chicago",
    titre: "Le neurone formel de McCulloch et Pitts",
    texte: "Warren McCulloch et Walter Pitts, logicien autodidacte de 20 ans, décrivent le neurone comme une unité qui « s’allume » quand elle reçoit assez de signaux. En reliant de tels neurones, on peut réaliser des opérations logiques. C’est l’ancêtre des réseaux de neurones artificiels qui font tourner les IA d’aujourd’hui… même si un vrai neurone est bien plus complexe.",
  },
  {
    theme: "tech",
    annee: 1950,
    lieu: "Revue Mind, octobre",
    titre: "Le test de Turing",
    texte: "Plutôt que de définir la pensée, Turing propose une épreuve : si un juge qui dialogue par écrit ne parvient pas à distinguer la machine d’un humain, pourquoi ne pas dire qu’elle pense ? Il prédit que vers l’an 2000, les machines tromperont souvent les juges. En 2025, une étude rapporte que GPT-4.5, invité à jouer un personnage, a été pris pour un humain dans 73 % des cas.",
  },
  {
    theme: "tech",
    annee: 1956,
    lieu: "Dartmouth College, été",
    titre: "L’atelier de Dartmouth",
    texte: "John McCarthy, Marvin Minsky, Claude Shannon et Nathaniel Rochester affirment que chaque aspect de l’intelligence peut, en principe, être décrit assez précisément pour qu’une machine le simule. Ils espèrent avancer nettement… en un seul été, avec une dizaine de chercheurs, tous des hommes. Le terme choisi par McCarthy s’impose, malgré les critiques.",
  },
  {
    theme: "tech",
    annee: 1958,
    lieu: "Washington, juillet",
    titre: "Le Perceptron",
    texte: "Au lieu de suivre des règles écrites à la main, le Perceptron ajuste les connexions de ses neurones artificiels à partir d’exemples. La presse s’emballe : on annonce des machines qui marcheront, parleront et auront conscience d’elles-mêmes ! En 1969, Minsky et Papert démontrent ses limites ; l’intérêt pour les réseaux de neurones s’effondre pour longtemps.",
  },
  {
    theme: "tech",
    annee: 1972,
    lieu: "Marseille-Luminy",
    titre: "Prolog et l’IA symbolique",
    texte: "Avec Philippe Roussel, Alain Colmerauer conçoit Prolog (PROgrammation en LOGique) : on décrit des faits et des règles, la machine en déduit les conséquences. C’est l’essor de l’IA symbolique : dans les années 1980, les « systèmes experts », qui codent le savoir de spécialistes, gagnent les entreprises. Coûteux et rigides, ils déçoivent : c’est un nouvel « hiver de l’IA ».",
  },
  {
    theme: "tech",
    annee: 1989,
    lieu: "Laboratoires Bell, New Jersey",
    titre: "Les réseaux convolutifs de Yann LeCun",
    texte: "Le Français Yann LeCun entraîne un réseau de neurones « convolutif », inspiré du cortex visuel, grâce à la rétropropagation du gradient, popularisée en 1986. À la fin des années 1990, ses descendants lisent une bonne part des chèques aux États-Unis. Longtemps délaissée, l’approche triomphera en 2012. LeCun recevra le prix Turing avec Geoffrey Hinton et Yoshua Bengio.",
  },
  {
    theme: "tech",
    annee: 1997,
    lieu: "New York, 11 mai",
    titre: "Deep Blue contre Kasparov",
    texte: "Battu l’année précédente, Deep Blue prend sa revanche 3,5 à 2,5. Sa force : examiner environ 200 millions de positions par seconde, guidé par des connaissances affinées avec des grands maîtres. Il ne « comprend » pas le jeu : il calcule. Kasparov soupçonne même une aide humaine. Le symbole frappe les esprits : la machine bat l’humain sur un terrain réputé intellectuel.",
  },
  {
    theme: "tech",
    annee: 2012,
    lieu: "Université de Toronto",
    titre: "AlexNet, le déclic de l’apprentissage profond",
    texte: "Conçu par Alex Krizhevsky, Ilya Sutskever et Geoffrey Hinton, AlexNet fait 15 % d’erreurs, contre 26 % pour le suivant. Trois ingrédients : un réseau profond, des cartes graphiques de jeu vidéo et ImageNet, 14 millions d’images réunies par l’équipe de Fei-Fei Li et étiquetées par des dizaines de milliers de travailleurs du clic. L’apprentissage profond est lancé.",
  },
  {
    theme: "tech",
    annee: 2017,
    lieu: "Google, juin",
    titre: "Le Transformer",
    texte: "Pour traiter un mot, ce nouveau type de réseau de neurones pèse l’importance de tous les autres mots du texte, en parallèle : c’est le mécanisme d’« attention ». Conçu pour la traduction, il se révèle universel : texte, images, son, code… C’est le « T » de GPT. Presque tous les grands modèles de langage en descendent, et la plupart des auteurs ont depuis fondé leur start-up.",
  },
  {
    theme: "tech",
    annee: 2024,
    lieu: "Stockholm, 8 et 9 octobre",
    titre: "L’IA au palmarès des Nobel",
    texte: "Le Nobel de physique distingue John Hopfield et Geoffrey Hinton pour leurs travaux fondateurs sur les réseaux de neurones artificiels. Le lendemain, celui de chimie récompense notamment Demis Hassabis et John Jumper (Google DeepMind) pour AlphaFold, une IA qui prédit la forme 3D des protéines, un défi vieux de 50 ans. Hinton en profite pour alerter sur les risques de l’IA.",
  },

  /* ===== BIAIS ===== */
  {
    theme: "bia",
    annee: 1988,
    lieu: "Londres",
    titre: "Le logiciel de sélection de St George’s",
    texte: "Dès 1982, l’école confie tout le premier tri des candidatures à un programme qui reproduit à 90-95 % les choix de son jury… préjugés compris : il attribue des notes plus basses aux femmes et aux noms à consonance non européenne. Deux enseignants alertent la Commission pour l’égalité raciale fin 1986. Son rapport de 1988 conclut à une discrimination : une soixantaine de candidats par an étaient privés d’entretien.",
  },
  {
    theme: "bia",
    annee: 2015,
    lieu: "États-Unis, juin",
    titre: "L’erreur de Google Photos",
    texte: "Le développeur Jacky Alciné découvre que le classement automatique a rangé des photos de lui et d’une amie sous cette étiquette. Google s’excuse aussitôt. Trois ans plus tard, une enquête révèle que sa « correction » a surtout consisté à supprimer les étiquettes « gorille », « chimpanzé » et « singe ». Signe que le problème de fond n’était pas résolu.",
  },
  {
    theme: "bia",
    annee: 2016,
    lieu: "ProPublica, mai",
    titre: "COMPAS et la « justice prédictive »",
    texte: "COMPAS attribue à chaque accusé un score de risque de récidive, consulté par les juges. ProPublica analyse 7 000 cas en Floride : parmi les personnes qui n’ont pas récidivé, les accusés noirs ont été presque deux fois plus souvent classés « à risque » que les blancs. L’éditeur conteste. Le débat révèle plusieurs définitions mathématiques de l’équité, impossibles à satisfaire toutes à la fois.",
  },
  {
    theme: "bia",
    annee: 2018,
    lieu: "MIT, février",
    titre: "L’étude « Gender Shades »",
    texte: "Joy Buolamwini et Timnit Gebru testent les logiciels d’IBM, Microsoft et Face++ chargés de deviner le genre sur une photo. Erreurs : moins de 1 % pour les hommes à peau claire, jusqu’à 35 % pour les femmes à peau foncée. En cause, des données d’entraînement peu représentatives. En 2020, IBM, Amazon et Microsoft cessent ou suspendent la vente de reconnaissance faciale à la police américaine.",
  },
  {
    theme: "bia",
    annee: 2018,
    lieu: "Reuters, octobre",
    titre: "L’outil de recrutement d’Amazon",
    texte: "Depuis 2014, Amazon testait un outil notant les CV d’une à cinq étoiles, entraîné sur dix ans de candidatures reçues, surtout masculines. L’IA en a déduit que les hommes étaient préférables : elle pénalisait les CV contenant le mot « women’s », comme « capitaine du club d’échecs féminin », et ceux de diplômées de deux universités pour femmes. Malgré des corrections, Amazon renonce au projet.",
  },
  {
    theme: "bia",
    annee: 2019,
    lieu: "Revue Science, octobre",
    titre: "Le biais caché d’un algorithme de santé",
    texte: "Pour repérer les malades qui ont besoin d’un suivi renforcé, l’algorithme prédit… leurs futures dépenses de santé. Or, à besoins égaux, on dépense moins pour les patients noirs, qui accèdent plus difficilement aux soins : ils doivent être plus malades pour être sélectionnés. En changeant la variable à prédire, la part de patients noirs orientés passerait de 18 % à 47 %.",
  },
  {
    theme: "bia",
    annee: 2020,
    lieu: "Detroit, janvier",
    titre: "Robert Williams, arrêté par erreur",
    texte: "La police de Detroit soumet à un logiciel de reconnaissance faciale l’image floue d’un voleur de montres. Le logiciel désigne Robert Williams, arrêté devant chez lui sous les yeux de ses filles et détenu une trentaine d’heures : le premier cas connu d’arrestation injustifiée due à cette technologie aux États-Unis. En 2024, Detroit s’engage à ne plus arrêter personne sur la seule foi d’une correspondance.",
  },
  {
    theme: "bia",
    annee: 2020,
    lieu: "Angleterre, août",
    titre: "Le scandale des A-levels",
    texte: "Faute d’examens à cause du Covid-19, les notes de l’équivalent du bac sont calculées par un algorithme qui tient compte des résultats passés de chaque lycée. Près de 40 % des notes proposées par les enseignants sont revues à la baisse, surtout dans les lycées publics défavorisés. Face à la colère des élèves, le gouvernement fait marche arrière en quatre jours.",
  },
  {
    theme: "bia",
    annee: 2020,
    lieu: "Bologne, 31 décembre",
    titre: "Frank, l’algorithme de Deliveroo",
    texte: "L’algorithme « Frank » notait chaque livreur selon sa fiabilité et sa participation : les mieux notés choisissaient leurs créneaux en priorité. Mais il pénalisait toute absence, sans distinguer une grève ou une maladie d’un motif moins sérieux. Saisi par des syndicats, le tribunal condamne Deliveroo à verser 50 000 euros ; l’entreprise répond que l’algorithme n’est plus utilisé. Une première en Europe.",
  },
  {
    theme: "bia",
    annee: 2023,
    lieu: "France, 27 novembre",
    titre: "Le score de risque de la CAF",
    texte: "Pour cibler ses contrôles, la Caisse nationale des allocations familiales calcule chaque mois plus de 13 millions de scores de risque. En analysant le code d’anciennes versions, La Quadrature du Net montre que le score augmente avec la précarité (RSA, quartier « défavorisé »…). En 2024, quinze organisations saisissent le Conseil d’État. Aux Pays-Bas, un scandale comparable avait fait tomber le gouvernement en 2021.",
  },
  {
    theme: "bia",
    annee: 2024,
    lieu: "Google, février",
    titre: "Les images de Gemini",
    texte: "Pour éviter de ne représenter que des hommes blancs, Gemini avait été réglé pour diversifier les personnes qu’il dessine. Résultat : des soldats allemands de 1943 ou des pères fondateurs des États-Unis d’origines variées, historiquement faux. Face au tollé, Google suspend la génération de personnes et reconnaît des erreurs inacceptables. Corriger un biais sans tenir compte du contexte peut en créer un autre.",
  },
  {
    theme: "bia",
    annee: 2024,
    lieu: "Revue Nature, 28 août",
    titre: "Les préjugés cachés des modèles de langage",
    texte: "Des chercheurs soumettent à des modèles comme GPT-4 les mêmes propos, en anglais standard ou en anglais afro-américain. Sans que l’origine soit jamais mentionnée, les modèles associent le second à des métiers moins prestigieux et, dans des procès fictifs, condamnent plus souvent ses locuteurs. Leurs réponses explicites sont pourtant antiracistes : l’entraînement à « bien répondre » masque les stéréotypes sans les effacer.",
  },

  /* ===== ENVIRONNEMENT ===== */
  {
    theme: "env",
    annee: 1922,
    lieu: "Publié à Cambridge (Royaume-Uni)",
    titre: "L’usine à prévisions de Richardson",
    texte: "Ambulancier en Champagne pendant la Première Guerre mondiale, Lewis Fry Richardson résout à la main les équations de l’atmosphère. Sa prévision, publiée en 1922, est fausse, mais sa méthode est la bonne. Il rêve d’une « usine à prévisions » de 64 000 calculateurs humains. En 1950, l’ENIAC réussit la première prévision numérique ; aujourd’hui, des IA prévoient dix jours en une minute.",
  },
  {
    theme: "env",
    annee: 1972,
    lieu: "MIT, pour le Club de Rome",
    titre: "« Les Limites à la croissance »",
    texte: "Commandé par le Club de Rome, le rapport de Donella et Dennis Meadows simule sur ordinateur l’évolution de la population, de la production et des ressources. Si rien ne change, le modèle World3 annonce un déclin brutal au cours du XXIe siècle. Très critiqué à sa sortie et traduit dans une trentaine de langues, il est encore régulièrement confronté aux données réelles.",
  },
  {
    theme: "env",
    annee: 2016,
    lieu: "Google DeepMind, 20 juillet",
    titre: "L’IA refroidit les centres de données",
    texte: "Les serveurs chauffent, et leur refroidissement pèse lourd dans la facture d’électricité. Le système de DeepMind apprend à partir de milliers de capteurs et recommande les réglages des pompes et des ventilateurs : l’énergie consacrée au refroidissement baisse jusqu’à 40 %. Depuis 2018, l’IA pilote elle-même ces réglages dans plusieurs sites. Reste à savoir si ces gains compensent la croissance des usages.",
  },
  {
    theme: "env",
    annee: 2019,
    lieu: "Université du Massachusetts, juin",
    titre: "Le coût carbone des modèles de langage",
    texte: "Emma Strubell et ses collègues mesurent l’énergie nécessaire pour entraîner des modèles de traitement du langage. Dans le cas le plus extrême, l’empreinte atteint 284 tonnes de CO₂. Le chiffre est discuté, mais l’alerte est lancée dans la communauté scientifique. Depuis, l’enjeu a changé d’échelle : il ne s’agit plus d’un seul modèle, mais de milliards de requêtes chaque jour.",
  },
  {
    theme: "env",
    annee: 2022,
    lieu: "IDRIS (CNRS), 3 novembre",
    titre: "Le bilan carbone de BLOOM",
    texte: "Conçu par le collectif BigScience, un millier de chercheurs, BLOOM est entraîné sur le supercalculateur public Jean Zay. L’étude de Sasha Luccioni, Sylvain Viguier et Anne-Laure Ligozat estime son empreinte à environ 25 tonnes de CO₂ pour l’électricité, le double en comptant la fabrication du matériel et l’énergie au repos. Grâce à une électricité peu carbonée, c’est bien moins que les estimations pour GPT-3.",
  },
  {
    theme: "env",
    annee: 2023,
    lieu: "Revue Science, 14 novembre",
    titre: "GraphCast, la météo par l’IA",
    texte: "Entraîné sur près de 40 ans d’archives météorologiques, GraphCast (Google DeepMind) calcule une prévision à dix jours en moins d’une minute, quand les modèles physiques mobilisent des heures de supercalculateur. Il fait mieux que la référence européenne sur 90 % des indicateurs testés. En 2025, le Centre européen de prévision met en service son propre modèle d’IA, toujours nourri par les données des modèles physiques.",
  },
  {
    theme: "env",
    annee: 2024,
    lieu: "Rapport annuel, 2 juillet",
    titre: "Les émissions de Google s’envolent",
    texte: "Google déclare 14,3 millions de tonnes équivalent CO₂ émises en 2023 : 48 % de plus qu’en 2019 et 13 % de plus qu’en 2022. En cause, selon l’entreprise : l’énergie consommée par ses centres de données et les émissions de sa chaîne d’approvisionnement ; l’essor de l’IA rend son objectif climatique pour 2030 plus difficile à atteindre. Microsoft annonce de son côté 29 % de hausse depuis 2020.",
  },
  {
    theme: "env",
    annee: 2024,
    lieu: "Pennsylvanie, 20 septembre",
    titre: "L’IA relance… le nucléaire",
    texte: "Fermé en 2019, ce réacteur voisin de celui accidenté en 1979 doit redémarrer pour fournir à Microsoft de l’électricité bas carbone pendant 20 ans. Google et Amazon signent eux aussi des accords nucléaires. Selon l’Agence internationale de l’énergie, les centres de données ont consommé environ 1,5 % de l’électricité mondiale en 2024, une consommation qui pourrait plus que doubler d’ici 2030.",
  },
  {
    theme: "env",
    annee: 2024,
    lieu: "Revue Nature Computational Science, fin octobre",
    titre: "Les déchets électroniques de l’IA",
    texte: "Serveurs, cartes graphiques, mémoires : le matériel de l’IA est remplacé à un rythme effréné par des puces plus puissantes. Selon l’étude, les déchets accumulés d’ici 2030 pourraient atteindre 1,2 à 5 millions de tonnes, riches en métaux précieux et en substances toxiques. Prolonger la durée de vie des équipements et réutiliser leurs composants en éviterait une grande partie.",
  },
  {
    theme: "env",
    annee: 2025,
    lieu: "Paris, 22 juillet",
    titre: "Le cycle de vie de Mistral Large 2",
    texte: "Avec Carbone 4 et l’ADEME, Mistral AI publie ce qu’elle présente comme la première analyse complète du cycle de vie d’un modèle d’IA. Bilan arrêté en janvier 2025 : environ 20 400 tonnes équivalent CO₂ et 281 000 m³ d’eau pour Mistral Large 2. Une réponse de 400 tokens de l’assistant Le Chat représente 1,14 g de CO₂e et 45 mL d’eau. Peu à l’unité… beaucoup à l’échelle de milliards de requêtes.",
  },
];
