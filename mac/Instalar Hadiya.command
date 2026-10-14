#!/bin/bash
# Double-click to install or update Hadiya for this Mac user (no admin needed).
"$(dirname "$0")/mac/install.sh" || { echo; echo "La instalacion ha fallado. Mira el mensaje de arriba."; read -n 1 -s -r -p "Pulsa una tecla para cerrar"; exit 1; }
