#!/usr/bin/env python3
"""Simulateur des API HTTP exposées par les Raspberry Pi de la maquette.

Reproduit les deux endpoints que `interface/dashboard/views.py` interroge
sur chaque Raspberry Pi, pour pouvoir démontrer le fonctionnement de la
plateforme sans le rack physique :

  - GET  /metrics/temperature  -> métriques système instantanées
  - POST /ollama/generate      -> génération de texte façon Ollama, en
    streaming NDJSON

Chaque rack simulé a son propre modèle thermique (vitesse de chauffe/
refroidissement, seuil de ralentissement, seuil de « plantage ») reflétant
son type de refroidissement, afin que la démo reste pédagogique.

Ne dépend que de la bibliothèque standard (voir launcher/control_panel.py,
qui lance ce script et bascule Django dessus via la variable
d'environnement PI_SIMULATOR).

Utilisation autonome :
    python simulator/pi_simulator.py
"""

from __future__ import annotations

import json
import random
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

# --------------------------------------------------------------------------
# Profils des 3 racks — noms alignés sur RASPBERRIES dans
# interface/dashboard/views.py, ports alignés sur SIMULATOR_PORTS dans le
# même fichier.
# --------------------------------------------------------------------------

PROFILES = [
    {
        "name": "Refroidissement passif ♨️",
        "port": 8001,
        "idle_temp": 38.0,
        "warm_rate": 0.18,
        "cool_rate": 0.14,
        "max_temp": 70.0,
        "throttle_temp": None,
        "crash_temp": None,
        "crash_chance": 0.0,
        "tokens_per_sec": 7.5,
        "tokens_per_sec_throttled": 7.5,
        "cpu_load_idle": (3, 8),
        "cpu_load_busy": (85, 100),
        "cpu_freq_idle": 600,
        "cpu_freq_busy": 1500,
        "ram_base": 28,
    },
    {
        "name": "Refroidissement actif air 🍃",
        "port": 8002,
        "idle_temp": 33.0,
        "warm_rate": 0.08,
        "cool_rate": 0.22,
        "max_temp": 55.0,
        "throttle_temp": None,
        "crash_temp": None,
        "crash_chance": 0.0,
        "tokens_per_sec": 8.0,
        "tokens_per_sec_throttled": 8.0,
        "cpu_load_idle": (3, 8),
        "cpu_load_busy": (85, 100),
        "cpu_freq_idle": 600,
        "cpu_freq_busy": 1500,
        "ram_base": 28,
    },
    {
        "name": "Refroidissement actif eau 💧",
        "port": 8003,
        "idle_temp": 28.0,
        "warm_rate": 0.05,
        "cool_rate": 0.30,
        "max_temp": 45.0,
        "throttle_temp": None,
        "crash_temp": None,
        "crash_chance": 0.0,
        "tokens_per_sec": 8.5,
        "tokens_per_sec_throttled": 8.5,
        "cpu_load_idle": (3, 8),
        "cpu_load_busy": (85, 100),
        "cpu_freq_idle": 600,
        "cpu_freq_busy": 1500,
        "ram_base": 28,
    },
]

# Vocabulaire utilisé pour fabriquer un faux texte généré token par token
# (thème datacenter/IA pour rester cohérent avec la démo).
FILLER_WORDS = (
    "le fonctionnement d'un centre de données repose sur un équilibre "
    "constant entre puissance de calcul et dissipation thermique il faut "
    "surveiller la température la charge processeur et la consommation "
    "électrique pour garantir la fiabilité du service chaque rack "
    "possède ses propres contraintes de refroidissement et un modèle de "
    "langage local permet de traiter les requêtes sans dépendre d'un "
    "service distant ce qui réduit la latence mais augmente la charge "
    "sur le matériel embarqué la gestion de l'énergie reste un enjeu "
    "majeur pour les infrastructures numériques de demain"
).split()


class PiState:
    """État thermique/charge d'un rack simulé, partagé entre les requêtes
    concurrentes (métriques pollées pendant qu'une génération est en cours)."""

    def __init__(self, profile: dict):
        self.profile = profile
        self.temp = profile["idle_temp"]
        self.last_update = time.monotonic()
        self.active_generations = 0
        self.lock = threading.Lock()

    def _advance_locked(self) -> float:
        """Fait avancer le modèle thermique jusqu'à maintenant. Le lock doit
        déjà être tenu par l'appelant."""
        now = time.monotonic()
        elapsed = max(0.0, now - self.last_update)
        self.last_update = now
        rate = self.profile["warm_rate"] if self.active_generations > 0 else -self.profile["cool_rate"]
        floor = self.profile["idle_temp"] - 2.0
        ceiling = self.profile["max_temp"] + 8.0
        self.temp = max(floor, min(ceiling, self.temp + rate * elapsed))
        return self.temp

    def read_temp(self) -> float:
        with self.lock:
            return round(self._advance_locked() + random.uniform(-0.3, 0.3), 1)

    def current_temp_locked(self) -> float:
        """À appeler avec `self.lock` déjà tenu (boucle de génération)."""
        return self._advance_locked()

    def enter_generation(self) -> None:
        with self.lock:
            self._advance_locked()
            self.active_generations += 1

    def exit_generation(self) -> None:
        with self.lock:
            self._advance_locked()
            self.active_generations = max(0, self.active_generations - 1)

    def is_busy(self) -> bool:
        with self.lock:
            return self.active_generations > 0


STATES = {p["name"]: PiState(p) for p in PROFILES}


def _metrics_payload(state: PiState) -> dict:
    profile = state.profile
    temp = state.read_temp()
    busy = state.is_busy()

    lo, hi = profile["cpu_load_busy"] if busy else profile["cpu_load_idle"]
    cpu_load = round(random.uniform(lo, hi), 1)

    freq = profile["cpu_freq_busy"] if busy else profile["cpu_freq_idle"]
    if profile["throttle_temp"] is not None and temp >= profile["throttle_temp"]:
        freq = int(freq * 0.6)  # le SoC réduit sa fréquence pour limiter la chauffe
    cpu_freq = max(200, freq + random.randint(-20, 20))

    ram = profile["ram_base"] + (15 if busy else 0) + random.uniform(-2, 2)

    return {
        "temperature_c": temp,
        "ram_used_percent": round(max(0.0, min(100.0, ram)), 1),
        "cpu_load_percent": cpu_load,
        "cpu_freq_mhz": cpu_freq,
    }


def _generate_tokens(n: int) -> list[str]:
    words: list[str] = []
    while len(words) < n:
        words.extend(FILLER_WORDS)
    random.shuffle(words)
    return words[:n]


class PiHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    profile: dict
    state: PiState

    def log_message(self, fmt, *args):  # noqa: A003 - signature imposée par la stdlib
        print(f"[simulateur:{self.profile['name']}] {fmt % args}")

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/metrics/temperature":
            self._send_json(_metrics_payload(self.state))
        else:
            self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/ollama/generate":
            self._send_json({"error": "not found"}, status=404)
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            data = {}
        model = data.get("model", "falcon3:1b")

        self._stream_generation(model)

    def _send_chunk(self, data: bytes) -> None:
        self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")

    def _stream_generation(self, model: str) -> None:
        profile = self.profile
        state = self.state
        state.enter_generation()
        try:
            tokens = _generate_tokens(random.randint(35, 90))

            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            for i, token in enumerate(tokens):
                with state.lock:
                    temp = state.current_temp_locked()

                delay = 1.0 / profile["tokens_per_sec"]
                if profile["throttle_temp"] is not None and temp >= profile["throttle_temp"]:
                    delay = 1.0 / profile["tokens_per_sec_throttled"]
                time.sleep(delay)

                if (
                    profile["crash_temp"] is not None
                    and temp >= profile["crash_temp"]
                    and random.random() < profile["crash_chance"]
                ):
                    # Simule un plantage lié à la surchauffe : la connexion est
                    # coupée sans le chunk terminal. Côté Django, `requests`
                    # lève une exception que `call_ollama` traduit en réponse
                    # partielle ou en message d'erreur générique.
                    self.close_connection = True
                    try:
                        self.connection.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                    return

                text = (" " if i > 0 else "") + token
                self._send_chunk((json.dumps({"model": model, "response": text, "done": False}) + "\n").encode())

            self._send_chunk(
                (json.dumps({"model": model, "response": "", "done": True, "eval_count": len(tokens)}) + "\n").encode()
            )
            self._send_chunk(b"")  # chunk terminal (taille 0)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            state.exit_generation()


def _make_handler(profile: dict, state: PiState) -> type[PiHandler]:
    class _Handler(PiHandler):
        pass

    _Handler.profile = profile
    _Handler.state = state
    return _Handler


def main() -> None:
    servers = []
    for profile in PROFILES:
        state = STATES[profile["name"]]
        handler = _make_handler(profile, state)
        server = ThreadingHTTPServer(("127.0.0.1", profile["port"]), handler)
        servers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True, name=profile["name"]).start()
        print(f"[simulateur] {profile['name']} -> http://127.0.0.1:{profile['port']}")

    print("Simulateur prêt. Ctrl+C pour arrêter.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nArrêt du simulateur…")
        for server in servers:
            server.shutdown()


if __name__ == "__main__":
    main()
