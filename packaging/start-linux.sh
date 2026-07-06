#!/bin/bash
cd "$(dirname "$0")"
echo; echo "  Agilink Fiches Suiveuses — démarrage local"; echo "  =========================================="; echo
command -v docker >/dev/null 2>&1 || { echo "  [!] Docker requis. Installez Docker + docker compose, puis relancez."; exit 1; }
docker info >/dev/null 2>&1 || { echo "  [!] Le service Docker n'est pas démarré (sudo systemctl start docker)."; exit 1; }
grep -q "PASTE-YOUR-OPENROUTER-KEY-HERE" .env 2>/dev/null && { echo "  [!] Éditez .env : remplacez PASTE-YOUR-OPENROUTER-KEY-HERE (VLLM_API_KEY et CHAT_API_KEY)."; exit 1; }
echo "  Construction et démarrage (1er lancement : quelques minutes)…"
docker compose up -d --build || { echo "  [!] Échec du démarrage."; exit 1; }
echo "  Initialisation…"; sleep 25
xdg-open "http://localhost:3000" >/dev/null 2>&1 || echo "  Ouvrez http://localhost:3000 dans votre navigateur."
echo; echo "  Application prête : http://localhost:3000  (arrêt : ./stop.sh)"; echo
