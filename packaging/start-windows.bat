@echo off
title Agilink Fiches Suiveuses - Test local
cd /d "%~dp0"

echo(
echo   Agilink Fiches Suiveuses - demarrage local
echo   ==========================================
echo(

where docker >nul 2>nul
if errorlevel 1 (
  echo   [!] Docker Desktop est requis et n'a pas ete trouve.
  echo       1^) Installez-le : https://www.docker.com/products/docker-desktop
  echo       2^) Lancez Docker Desktop et attendez qu'il soit "Running"
  echo       3^) Relancez ce fichier.
  echo(
  pause
  exit /b 1
)

docker info >nul 2>nul
if errorlevel 1 (
  echo   [!] Docker Desktop est installe mais pas demarre.
  echo       Ouvrez Docker Desktop, attendez qu'il soit pret, puis relancez.
  echo(
  pause
  exit /b 1
)

findstr /C:"PASTE-YOUR-OPENROUTER-KEY-HERE" .env >nul 2>nul
if not errorlevel 1 (
  echo   [!] Cle API manquante. Ouvrez le fichier .env et remplacez
  echo       PASTE-YOUR-OPENROUTER-KEY-HERE par votre cle OpenRouter
  echo       (sur les 2 lignes VLLM_API_KEY et CHAT_API_KEY^), puis relancez.
  echo(
  pause
  exit /b 1
)

echo   Construction et demarrage (le 1er lancement prend quelques minutes)...
docker compose up -d --build
if errorlevel 1 ( echo   [!] Echec du demarrage. Voir les messages ci-dessus. & pause & exit /b 1 )

echo   Initialisation en cours...
timeout /t 25 /nobreak >nul
start "" http://localhost:3000

echo(
echo   Application prete :  http://localhost:3000
echo   Pour l'arreter : double-cliquez sur  stop-windows.bat
echo(
pause
