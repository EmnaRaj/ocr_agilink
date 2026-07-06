#!/bin/bash
cd "$(dirname "$0")"
echo "Arrêt d'Agilink (les données sont conservées)…"
docker compose down
echo "Arrêté. Relancez avec start-mac.command"
read -p "Entrée pour fermer…"
