#!/usr/bin/env bash
# Lance le panneau de contrôle de la maquette Data Center.
# Utilise le Python de l'environnement virtuel du projet (Tkinter y est
# disponible) mais reste un outil indépendant de la plateforme Django.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON="$REPO_ROOT/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
    PYTHON="python3"
fi

exec "$PYTHON" "$SCRIPT_DIR/control_panel.py"
