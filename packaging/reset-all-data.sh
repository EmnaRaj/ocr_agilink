#!/bin/bash
cd "$(dirname "$0")"
read -p "Supprimer TOUTES les données locales (fiches, scans) ? [oui/non] " a
[ "$a" = "oui" ] && docker compose down -v && echo "Données effacées." || echo "Annulé."
