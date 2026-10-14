#!/usr/bin/env bash
# Download a Trello attachment (they 401 without auth) into /tmp/trello-img/ and print the path.
# Needs ~/.config/flows/trello.env with TRELLO_KEY=... and TRELLO_TOKEN=...
set -euo pipefail
source "$HOME/.config/flows/trello.env"
url="$1"; out="/tmp/trello-img/$(echo "$url" | md5sum | cut -c1-8)-$(basename "${url%%\?*}")"
mkdir -p /tmp/trello-img
curl -fsSL -H "Authorization: OAuth oauth_consumer_key=\"$TRELLO_KEY\", oauth_token=\"$TRELLO_TOKEN\"" -o "$out" "$url"
echo "$out"
