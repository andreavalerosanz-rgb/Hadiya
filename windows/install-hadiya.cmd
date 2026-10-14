@echo off
rem Double-click to install or update Hadiya for this Windows user (no admin needed).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (echo. & echo La instalacion ha fallado. Mira el mensaje de arriba. & pause & exit /b 1)
