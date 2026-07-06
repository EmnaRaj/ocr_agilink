#!/bin/bash
# One-shot deploy on a FRESH Ubuntu 22.04+ VM. Run from the repo root as root/sudo:
#   bash deploy/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

command -v docker >/dev/null 2>&1 || { echo "→ installing Docker…"; curl -fsSL https://get.docker.com | sh; }

[ -f .env ] || { echo "!! Create .env first:  cp deploy/env.prod .env  then edit DOMAIN + the OpenRouter key."; exit 1; }
grep -q "PASTE-YOUR-OPENROUTER-KEY-HERE" .env && { echo "!! Set your OpenRouter key in .env (VLLM_API_KEY + CHAT_API_KEY)."; exit 1; }
grep -q "change-me.com" .env && { echo "!! Set DOMAIN in .env to your real domain."; exit 1; }

if command -v ufw >/dev/null 2>&1; then ufw allow 22 >/dev/null; ufw allow 80 >/dev/null; ufw allow 443 >/dev/null; yes | ufw enable >/dev/null 2>&1 || true; fi

echo "→ building + starting (first run takes a few minutes)…"
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build

DOMAIN=$(grep -E '^DOMAIN=' .env | cut -d= -f2)
echo
echo "✅ Deployed. Point an A record for  $DOMAIN  at this server's IP."
echo "   HTTPS is issued automatically. Then send the client:  https://$DOMAIN"
