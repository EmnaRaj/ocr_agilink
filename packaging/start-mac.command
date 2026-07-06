#!/bin/bash
# Double-click this file to start Agilink Fiches Suiveuses on your Mac.
cd "$(dirname "$0")"

echo
echo "  Agilink Fiches Suiveuses — démarrage local"
echo "  =========================================="
echo

if ! command -v docker >/dev/null 2>&1; then
  echo "  [!] Docker Desktop est requis et introuvable."
  echo "      1) Installez-le : https://www.docker.com/products/docker-desktop"
  echo "      2) Lancez Docker Desktop et attendez qu'il soit prêt"
  echo "      3) Relancez ce fichier."
  read -p "  Appuyez sur Entrée pour fermer…"
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "  [!] Docker Desktop n'est pas démarré. Ouvrez-le, attendez, puis relancez."
  read -p "  Appuyez sur Entrée pour fermer…"
  exit 1
fi

if grep -q "PASTE-YOUR-OPENROUTER-KEY-HERE" .env 2>/dev/null; then
  echo "  [!] Clé API manquante. Ouvrez le fichier .env et remplacez"
  echo "      PASTE-YOUR-OPENROUTER-KEY-HERE par votre clé OpenRouter"
  echo "      (lignes VLLM_API_KEY et CHAT_API_KEY), puis relancez."
  read -p "  Appuyez sur Entrée pour fermer…"
  exit 1
fi

echo "  Construction et démarrage (le 1er lancement prend quelques minutes)…"
docker compose up -d --build || { echo "  [!] Échec du démarrage."; read -p "  Entrée pour fermer…"; exit 1; }

echo "  Initialisation en cours…"
sleep 25
open "http://localhost:3000"

echo
echo "  Application prête :  http://localhost:3000"
echo "  Pour l'arrêter : double-cliquez sur  stop-mac.command"
echo
read -p "  Appuyez sur Entrée pour fermer cette fenêtre…"
