#!/usr/bin/env bash
# Copia el upgrade de Flows a /opt/flows (guarda copia en /opt/flows.bak) y reinicia el servicio de usuario.
set -euo pipefail
src="$(cd "$(dirname "$0")" && pwd)"
sudo cp -a /opt/flows /opt/flows.bak-$(date +%Y%m%d%H%M%S)
sudo install -m 644 "$src/server.py" "$src/index.html" "$src/DEPLOY.md" /opt/flows/
# GPU para Ollama por ROCm (opcional; ahora va por Vulkan): da acceso a /dev/kfd. Requiere cerrar sesión.
sudo usermod -aG render,video "$USER"
systemctl --user restart flows
echo "Hecho. Flows reiniciado en http://localhost:8787"
