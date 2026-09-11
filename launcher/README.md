# Panneau de contrôle de la maquette

Application de bureau indépendante de la plateforme Django (Tkinter,
bibliothèque standard uniquement) avec deux boutons :

- **▶ Démarrer** : lance `manage.py runserver` et ouvre un navigateur dédié
  sur `http://127.0.0.1:8000/`.
- **⏹ Arrêter tout** : ferme le navigateur, arrête le serveur Django, puis
  éteint (SSH + `shutdown -h now`) les 3 Raspberry Pi du rack.

## Fichiers

- `control_panel.py` — l'application (fenêtre + logique).
- `run.sh` — lance `control_panel.py` avec le bon interpréteur Python.
- `maquette-control.desktop` — icône de lancement pour le bureau Ubuntu.
  Une copie a été installée dans `~/Desktop/`.

## Icône sur le bureau

Le fichier a été copié dans `~/Desktop/maquette-control.desktop` et rendu
exécutable. Au premier double-clic, Nautilus (Fichiers) peut demander de
confirmer via un bandeau **« Faire confiance à ce programme »** / **« Lancer »**
(ou clic droit → *Autoriser le lancement*) — c'est normal, à faire une seule
fois.

## Hypothèses / prérequis pour le bouton « Arrêter tout »

Le bouton éteint les Raspberry Pi via SSH par mot de passe (utilisateur
`miai`), en s'appuyant sur l'utilitaire système `sshpass` (déjà installé sur
cette machine ; sinon `sudo apt install sshpass`). Le même mot de passe sert
pour la connexion SSH et pour le `sudo shutdown` distant.

Les identifiants sont dans `launcher/pi_credentials.py` — **ce fichier n'est
pas commité** (voir `.gitignore`), pour ne pas stocker de mot de passe en
clair dans l'historique Git. Un modèle est fourni dans
`pi_credentials.py.example` : le copier en `pi_credentials.py` et renseigner
les identifiants si ce fichier venait à manquer (ex. nouveau clone du dépôt).
Sans ce fichier, ou sans `sshpass`, le bouton journalise l'erreur et
n'éteint aucun Pi.

Si les identifiants ou les adresses IP changent, ajuster
`pi_credentials.py` et `RASPBERRY_PIS` en tête de `control_panel.py` (les IP
doivent rester cohérentes avec `RASPBERRIES` dans
`interface/dashboard/views.py`).

Les Raspberry Pi éteints doivent être rallumés manuellement (bouton
physique) — il n'y a pas de redémarrage à distance.

## Navigateur

Le navigateur est ouvert en plein écran (mode kiosque, sans barre d'adresse
ni fenêtre) dans un profil temporaire dédié, afin d'obtenir un processus
indépendant que l'application peut fermer elle-même : `firefox -kiosk
-profile … -new-instance`, ou à défaut `google-chrome --kiosk` / `chromium`.
Si aucun de ces navigateurs n'est installé, la page s'ouvre quand même via
le navigateur par défaut du système, mais elle ne peut alors pas être fermée
automatiquement par le bouton « Arrêter tout ».

En mode kiosque, il n'y a pas de bouton pour quitter le navigateur — c'est
le bouton « ⏹ Arrêter tout » du panneau de contrôle qui s'en charge.

## Lancer manuellement (sans l'icône)

```bash
./launcher/run.sh
```
