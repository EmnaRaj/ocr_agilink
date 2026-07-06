@echo off
cd /d "%~dp0"
echo Arret d'Agilink (les donnees sont conservees)...
docker compose down
echo Arrete. Relancez avec start-windows.bat
pause
