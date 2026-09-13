#!/usr/bin/env python3
"""Panneau de contrôle de la maquette « Data Center ».

Application de bureau indépendante de la plateforme Django : une petite
fenêtre avec deux boutons.

- « Démarrer » : lance le serveur Django (manage.py runserver) et ouvre
  automatiquement un navigateur sur la page du site.
- « Arrêter »  : ferme le navigateur, arrête le serveur Django, puis éteint
  (shutdown) les 3 Raspberry Pi du rack.

Ne dépend que de la bibliothèque standard de Python (Tkinter inclus), afin
de pouvoir tourner indépendamment de l'environnement virtuel du projet
Django — à l'exception de l'utilitaire système `sshpass`, utilisé pour
l'authentification par mot de passe SSH vers les Raspberry Pi. Lancée depuis
une icône sur le bureau (voir maquette-control.desktop et run.sh dans ce
même dossier).
"""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext
import webbrowser

try:
    from pi_credentials import SSH_USER, SSH_PASSWORD
except ImportError:
    SSH_USER = None
    SSH_PASSWORD = None

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DJANGO_DIR = REPO_ROOT / "interface"
MANAGE_PY = DJANGO_DIR / "manage.py"
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
LOGO_PATH = DJANGO_DIR / "dashboard" / "static" / "dashboard" / "images" / "miai.png"
LOGO_WIDTH = 220  # largeur cible affichée, en pixels

SERVER_HOST = "127.0.0.1"
SERVER_PORT = "8000"
SITE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}/"

# Doit rester cohérent avec RASPBERRIES dans interface/dashboard/views.py
RASPBERRY_PIS = [
    {"name": "Rack 1 — Sans refroidissement", "host": "192.168.137.10"},
    {"name": "Rack 2 — Refroidissement passif", "host": "192.168.137.11"},
    {"name": "Rack 3 — Refroidissement actif", "host": "192.168.137.12"},
]
# Identifiants SSH (utilisateur + mot de passe) : voir launcher/pi_credentials.py
# (non commité, cf. .gitignore et pi_credentials.py.example). Identiques sur
# les 3 Raspberry Pi (cf. ansible_folder/inventory.ini dans le dépôt
# maquette-data-center).
SSH_OPTS = [
    "-o", "ConnectTimeout=5",
    "-o", "NumberOfPasswordPrompts=1",
    "-o", "StrictHostKeyChecking=accept-new",
]

STOP_TIMEOUT = 5  # secondes avant de passer d'un arrêt propre (TERM) au KILL


def _port_is_open(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _pids_listening_on_port(port: int) -> list[int]:
    """Trouve les PID qui écoutent sur ce port TCP en lisant /proc directement
    (aucune dépendance à des outils externes comme fuser/lsof, pas toujours
    présents). Sert de filet de sécurité pour retrouver un serveur devenu
    orphelin (ex. application fermée brutalement lors d'une session
    précédente) et que cette instance ne connaît pas via self.server_proc.
    """
    target_hex = f"{port:04X}"
    inodes = set()
    for proc_net in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(proc_net) as f:
                next(f, None)  # en-tête
                for line in f:
                    fields = line.split()
                    if len(fields) < 10:
                        continue
                    local_addr, state, inode = fields[1], fields[3], fields[9]
                    hex_port = local_addr.rsplit(":", 1)[-1]
                    if hex_port.upper() == target_hex and state == "0A":  # 0A = LISTEN
                        inodes.add(inode)
        except OSError:
            continue
    if not inodes:
        return []

    pids = []
    for pid_dir in Path("/proc").iterdir():
        if not pid_dir.name.isdigit():
            continue
        fd_dir = pid_dir / "fd"
        try:
            fds = list(fd_dir.iterdir())
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            if target.startswith("socket:[") and target[8:-1] in inodes:
                pids.append(int(pid_dir.name))
                break
    return pids


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _kill_pids(pids: list[int], timeout: float = 5.0) -> None:
    """Envoie SIGTERM puis, passé timeout, SIGKILL aux PID encore en vie."""
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    deadline = time.monotonic() + timeout
    remaining = set(pids)
    while remaining and time.monotonic() < deadline:
        remaining = {p for p in remaining if _pid_alive(p)}
        if remaining:
            time.sleep(0.2)
    for pid in remaining:
        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


class ControlPanel:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.server_proc: subprocess.Popen | None = None
        self.browser_proc: subprocess.Popen | None = None
        self.browser_profile_dir: str | None = None
        self._stopping = False

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # -- UI ----------------------------------------------------------------

    def _build_ui(self) -> None:
        self.root.title("Maquette Data Center — Panneau de contrôle")
        self.root.geometry("560x420")
        self.root.minsize(480, 360)

        self.logo_image = self._load_logo()
        if self.logo_image is not None:
            self.root.iconphoto(True, self.logo_image)

        header_frame = tk.Frame(self.root)
        header_frame.pack(pady=(16, 4))

        if self.logo_image is not None:
            tk.Label(header_frame, image=self.logo_image).pack(side=tk.LEFT, padx=(0, 10))

        header = tk.Label(
            header_frame,
            text="Maquette Data Center",
            font=("Sans", 16, "bold"),
        )
        header.pack(side=tk.LEFT)

        self.status_var = tk.StringVar(value="● Arrêté")
        self.status_label = tk.Label(
            self.root, textvariable=self.status_var, font=("Sans", 11), fg="#b00020"
        )
        self.status_label.pack(pady=(0, 12))

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=4)

        self.start_btn = tk.Button(
            btn_frame,
            text="▶  Démarrer",
            font=("Sans", 12, "bold"),
            width=16,
            height=2,
            bg="#2e7d32",
            fg="white",
            command=self.start_server,
        )
        self.start_btn.grid(row=0, column=0, padx=8)

        self.stop_btn = tk.Button(
            btn_frame,
            text="■  Arrêter tout",
            font=("Sans", 12, "bold"),
            width=16,
            height=2,
            bg="#b00020",
            fg="white",
            state=tk.DISABLED,
            command=self.stop_all,
        )
        self.stop_btn.grid(row=0, column=1, padx=8)

        log_label = tk.Label(self.root, text="Journal :", anchor="w")
        log_label.pack(fill="x", padx=12, pady=(16, 0))

        self.log_widget = scrolledtext.ScrolledText(
            self.root, height=12, state=tk.DISABLED, font=("Monospace", 9)
        )
        self.log_widget.pack(fill="both", expand=True, padx=12, pady=(4, 12))

    def _load_logo(self) -> tk.PhotoImage | None:
        """Charge le logo miai.png et le réduit à une taille affichable
        (l'image source fait plus de 5000 px de large)."""
        if not LOGO_PATH.exists():
            return None
        try:
            img = tk.PhotoImage(file=str(LOGO_PATH))
            factor = max(1, img.width() // LOGO_WIDTH)
            if factor > 1:
                img = img.subsample(factor, factor)
            return img
        except tk.TclError as exc:
            self.log(f"Impossible de charger le logo ({exc}).")
            return None

    def log(self, message: str) -> None:
        """Ajoute une ligne horodatée au journal. Thread-safe."""

        def _do():
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_widget.configure(state=tk.NORMAL)
            self.log_widget.insert(tk.END, f"[{ts}] {message}\n")
            self.log_widget.see(tk.END)
            self.log_widget.configure(state=tk.DISABLED)

        self.root.after(0, _do)

    def _set_status(self, text: str, color: str) -> None:
        self.root.after(0, lambda: (self.status_var.set(text), self.status_label.configure(fg=color)))

    # -- Démarrage -----------------------------------------------------------

    def start_server(self) -> None:
        self.start_btn.configure(state=tk.DISABLED)
        self._set_status("● Démarrage…", "#e65100")
        self.log("Démarrage du serveur Django…")

        if not VENV_PYTHON.exists():
            self.log(f"Python introuvable : {VENV_PYTHON}")
            messagebox.showerror("Erreur", f"Interpréteur Python introuvable :\n{VENV_PYTHON}")
            self.start_btn.configure(state=tk.NORMAL)
            self._set_status("● Arrêté", "#b00020")
            return

        # Filet de sécurité : si un serveur d'une session précédente occupe
        # encore le port (ex. application fermée brutalement, sans passer
        # par « Arrêter tout »), on le libère avant de relancer — sinon le
        # nouveau processus échoue silencieusement et le bouton « Arrêter »
        # ne connaîtra jamais l'ancien serveur, qui ne s'arrêtera donc jamais.
        if _port_is_open(SERVER_HOST, int(SERVER_PORT)):
            self.log(f"Le port {SERVER_PORT} est déjà occupé (ancien serveur non arrêté ?), libération…")
            _kill_pids(_pids_listening_on_port(int(SERVER_PORT)))
            time.sleep(0.3)
            if _port_is_open(SERVER_HOST, int(SERVER_PORT)):
                self.log(f"Le port {SERVER_PORT} est toujours occupé par un autre programme.")
                messagebox.showerror(
                    "Port occupé",
                    f"Le port {SERVER_PORT} est utilisé par un autre programme.\n"
                    "Fermez-le puis réessayez.",
                )
                self.start_btn.configure(state=tk.NORMAL)
                self._set_status("● Arrêté", "#b00020")
                return
            self.log("Port libéré.")

        try:
            self.server_proc = subprocess.Popen(
                [
                    str(VENV_PYTHON),
                    str(MANAGE_PY),
                    "runserver",
                    f"{SERVER_HOST}:{SERVER_PORT}",
                    "--noreload",
                ],
                cwd=str(DJANGO_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,  # pour pouvoir tuer tout le groupe proprement
            )
        except OSError as exc:
            self.log(f"Impossible de lancer le serveur : {exc}")
            messagebox.showerror("Erreur", f"Impossible de lancer le serveur Django :\n{exc}")
            self.start_btn.configure(state=tk.NORMAL)
            self._set_status("● Arrêté", "#b00020")
            return

        threading.Thread(target=self._pipe_server_output, daemon=True).start()
        threading.Thread(target=self._wait_for_server_then_open_browser, daemon=True).start()

    def _pipe_server_output(self) -> None:
        proc = self.server_proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                self.log(f"[django] {line}")

    def _wait_for_server_then_open_browser(self, timeout: float = 20.0) -> None:
        proc = self.server_proc
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if proc is not None and proc.poll() is not None:
                self.log(f"Le serveur Django s'est arrêté prématurément (code {proc.returncode}).")
                self.root.after(0, self._reset_after_failed_start)
                return
            if _port_is_open(SERVER_HOST, int(SERVER_PORT)):
                self.log("Serveur Django prêt.")
                self._set_status("● En ligne", "#2e7d32")
                self.root.after(0, lambda: self.stop_btn.configure(state=tk.NORMAL))
                self.root.after(0, self._open_browser)
                return
            time.sleep(0.3)
        self.log("Le serveur met du temps à démarrer, ouverture du navigateur quand même…")
        self._set_status("● En ligne", "#2e7d32")
        self.root.after(0, lambda: self.stop_btn.configure(state=tk.NORMAL))
        self.root.after(0, self._open_browser)

    def _reset_after_failed_start(self) -> None:
        self.start_btn.configure(state=tk.NORMAL)
        self._set_status("● Arrêté", "#b00020")
        self.server_proc = None

    # -- Navigateur ------------------------------------------------------

    def _open_browser(self) -> None:
        self.log(f"Ouverture du navigateur sur {SITE_URL}")
        cmd = self._build_browser_command(SITE_URL)
        if cmd is None:
            self.log("Aucun navigateur dédié trouvé, ouverture via le navigateur par défaut "
                      "(il ne pourra pas être fermé automatiquement).")
            webbrowser.open(SITE_URL)
            return
        try:
            self.browser_proc = subprocess.Popen(cmd)
        except OSError as exc:
            self.log(f"Échec du lancement du navigateur ({exc}), tentative avec webbrowser.open().")
            webbrowser.open(SITE_URL)

    def _build_browser_command(self, url: str) -> list[str] | None:
        """Construit une commande de navigateur lancée dans un profil dédié,
        afin d'obtenir un processus séparé que l'on peut fermer nous-mêmes
        (plutôt que de se greffer sur une fenêtre de navigateur déjà ouverte).

        Le dossier est créé sous le répertoire personnel plutôt que dans
        /tmp : sur Ubuntu, Firefox est en général installé en paquet snap,
        qui tourne dans un bac à sable avec son propre /tmp isolé — un
        profil créé dans le /tmp de l'hôte lui est alors invisible (« profil
        introuvable »). $HOME reste accessible au snap, à condition de ne
        pas utiliser un dossier caché (préfixé par un point), lui aussi
        souvent restreint par le bac à sable.
        """
        parent = Path.home() / "maquette-launcher-browser-profiles"
        try:
            parent.mkdir(exist_ok=True)
        except OSError:
            parent = Path.home()
        self.browser_profile_dir = tempfile.mkdtemp(prefix="browser-profile-", dir=str(parent))

        path = shutil.which("firefox")
        if path:
            return [
                path,
                "-kiosk",
                "-profile", self.browser_profile_dir,
                "-new-instance",
                "-no-remote",
                url,
            ]

        for exe in ("google-chrome", "chromium-browser", "chromium"):
            path = shutil.which(exe)
            if path:
                return [
                    path,
                    "--kiosk",
                    url,
                    "--new-window",
                    f"--user-data-dir={self.browser_profile_dir}",
                    "--no-first-run",
                ]

        return None

    # -- Arrêt ---------------------------------------------------------------

    def stop_all(self) -> None:
        if self._stopping:
            return
        confirmed = messagebox.askyesno(
            "Confirmer l'arrêt",
            "Cela va arrêter le serveur, fermer le navigateur et ÉTEINDRE les 3 "
            "Raspberry Pi.\n\nIl faudra les rallumer manuellement (bouton "
            "physique) pour la prochaine session.\n\nContinuer ?",
        )
        if not confirmed:
            return

        self._stopping = True
        self.stop_btn.configure(state=tk.DISABLED)
        threading.Thread(target=self._do_stop_all, daemon=True).start()

    def _do_stop_all(self) -> None:
        self.log("Arrêt en cours…")
        self._set_status("● Arrêt en cours…", "#e65100")

        self._stop_browser()
        self._stop_server()
        self._shutdown_all_pis()

        self.log("Arrêt terminé.")
        self._set_status("● Arrêté", "#b00020")
        self._stopping = False
        self.root.after(0, lambda: self.start_btn.configure(state=tk.NORMAL))

    def _stop_browser(self) -> None:
        if self.browser_proc is not None and self.browser_proc.poll() is None:
            self.log("Fermeture du navigateur…")
            self._terminate_then_kill(self.browser_proc)
        self.browser_proc = None
        if self.browser_profile_dir:
            shutil.rmtree(self.browser_profile_dir, ignore_errors=True)
            self.browser_profile_dir = None

    def _stop_server(self) -> None:
        if self.server_proc is not None and self.server_proc.poll() is None:
            self.log("Arrêt du serveur Django…")
            try:
                os.killpg(os.getpgid(self.server_proc.pid), signal.SIGTERM)
                self.server_proc.wait(timeout=STOP_TIMEOUT)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(os.getpgid(self.server_proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.log("Serveur Django arrêté.")
        self.server_proc = None

        # Filet de sécurité : un serveur laissé orphelin par une session
        # précédente (application fermée brutalement, plantée, ou deux
        # démarrages successifs) peut encore écouter sur le port sans que
        # cette instance en ait la main via self.server_proc.
        leftover = _pids_listening_on_port(int(SERVER_PORT))
        if leftover:
            self.log(f"Processus restant sur le port {SERVER_PORT} ({leftover}), arrêt forcé…")
            _kill_pids(leftover, timeout=STOP_TIMEOUT)
            if _pids_listening_on_port(int(SERVER_PORT)):
                self.log(f"Le port {SERVER_PORT} semble toujours occupé.")
            else:
                self.log("Serveur orphelin arrêté.")

    @staticmethod
    def _terminate_then_kill(proc: subprocess.Popen) -> None:
        try:
            proc.terminate()
            proc.wait(timeout=STOP_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
        except ProcessLookupError:
            pass

    def _shutdown_all_pis(self) -> None:
        if not SSH_USER or not SSH_PASSWORD:
            self.log(
                "Identifiants SSH introuvables (launcher/pi_credentials.py manquant) : "
                "Raspberry Pi non éteints."
            )
            return
        sshpass_path = shutil.which("sshpass")
        if not sshpass_path:
            self.log(
                "'sshpass' n'est pas installé (sudo apt install sshpass) : "
                "Raspberry Pi non éteints."
            )
            return

        self.log("Extinction des Raspberry Pi…")
        with ThreadPoolExecutor(max_workers=len(RASPBERRY_PIS) or 1) as pool:
            list(pool.map(lambda pi: self._shutdown_one_pi(pi, sshpass_path), RASPBERRY_PIS))

    def _shutdown_one_pi(self, pi: dict, sshpass_path: str) -> None:
        name, host = pi["name"], pi["host"]
        # Le mot de passe sert à la fois pour la connexion SSH (via sshpass)
        # et pour le sudo distant (fourni sur son entrée standard).
        remote_cmd = f"echo {shlex.quote(SSH_PASSWORD)} | sudo -S -p '' shutdown -h now"
        cmd = [
            sshpass_path, "-p", SSH_PASSWORD,
            "ssh", *SSH_OPTS, f"{SSH_USER}@{host}", remote_cmd,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        except subprocess.TimeoutExpired:
            self.log(f"{name} ({host}) : délai dépassé, injoignable.")
            return
        except OSError as exc:
            self.log(f"{name} ({host}) : erreur ssh ({exc}).")
            return

        if result.returncode == 0:
            self.log(f"{name} ({host}) : extinction demandée.")
        else:
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            detail = detail[-1] if detail else f"code {result.returncode}"
            self.log(f"{name} ({host}) : échec ({detail}).")

    # -- Fermeture de la fenêtre ---------------------------------------------

    def on_close(self) -> None:
        # Fermer la fenêtre arrête le serveur et le navigateur (pour ne pas
        # laisser de processus orphelins), mais n'éteint PAS les Raspberry Pi
        # — seul le bouton « Arrêter tout » le fait explicitement.
        if self.server_proc is not None and self.server_proc.poll() is None:
            self._stop_server()
        if self.browser_proc is not None and self.browser_proc.poll() is None:
            self._stop_browser()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    ControlPanel(root)
    root.mainloop()


if __name__ == "__main__":
    main()
