#!/usr/bin/env bash
# Usage (as the person, not root): setup-token-optimizer.sh
# Installs the Token Optimizer plugin into this user's ~/.claude. Hooks then run in every Hadiya session they own.
set -euo pipefail
claude plugin marketplace add alexgreensh/token-optimizer 2>&1 | tail -1 || true
claude plugin install token-optimizer@alexgreensh-token-optimizer 2>&1 | tail -1
M=$(ls -d ~/.claude/plugins/cache/alexgreensh-token-optimizer/token-optimizer/*/skills/token-optimizer/scripts/measure.py | tail -1)
python3 "$M" doctor | tail -4
