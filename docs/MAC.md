# Hadiya en Mac

> **Para quien prepara el paquete**
> 1. Ejecuta `bash scripts/build-mac.sh`.
> 2. Se crea `dist/hadiya-macos_<ver>.zip` (o descárgalo de la [última release](https://github.com/andreavalerosanz-rgb/flows/releases/latest)).
> 3. Envía ese zip a la persona. Nada más.

Hadiya es un panel que se abre en tu Mac para trabajar con Claude Code. Todo funciona en **este Mac** y con tu propia cuenta de Claude (plan de pago).

## Qué necesitas

- macOS 12 o más nuevo, Apple Silicon o Intel.
- Internet durante la instalación.
- No hace falta ser administrador.

## Instalar

1. Descarga `hadiya-macos_<ver>.zip` y haz doble clic para descomprimirlo (carpeta `Hadiya`).
2. Haz **clic derecho** sobre **Instalar Hadiya.command** → **Abrir** → **Abrir**.
   - Es necesario porque el archivo no está firmado por Apple y macOS bloquea los ficheros descargados (Gatekeeper). Si solo dice "no se puede abrir", ve a **Ajustes del Sistema → Privacidad y seguridad → Abrir igualmente**.
   - Alternativa en Terminal: `xattr -dr com.apple.quarantine ~/Downloads/Hadiya` y después doble clic.
   - Si el doble clic no hace nada (el zip perdió el permiso de ejecución): `bash ~/Downloads/Hadiya/mac/install.sh`.
3. Se abre Terminal y el instalador trabaja unos minutos:
   - **Python**: usa el que ya tengas (Homebrew, python.org o Herramientas de línea de comandos). Si no hay ninguno, descarga una copia privada con [uv](https://astral.sh/uv) en tu carpeta de usuario, sin Homebrew ni admin.
   - **Claude Code**: con el instalador oficial (`claude.ai/install.sh`), en `~/.local/bin`.
   - **Hadiya**: en `~/Library/Application Support/Hadiya/app`; tus datos, en `.../Hadiya/data`.
   - Un servicio de usuario (LaunchAgent `com.hadiya.server`) que arranca Hadiya al iniciar sesión.
   - La app **Hadiya** en `~/Applications` (tu carpeta de usuario), que abre Hadiya en su propia ventana (Chrome, Edge o Brave; si no hay, el navegador por defecto).
4. La primera vez se abre el navegador para que entres en tu cuenta de Claude (`claude auth login`). Se hace una sola vez.
5. Se abre Hadiya. Ya está.

## Uso diario

Abre **Hadiya** desde Launchpad/Spotlight o `~/Applications`. El servidor ya estará en marcha desde que iniciaste sesión. Log: `~/Library/Application Support/Hadiya/data/server.log`.

## Actualizar

Descarga el zip nuevo, descomprímelo y repite la instalación. Se reemplaza la aplicación, **se conservan tus datos** y se reinicia el servicio.

## Desinstalar

```
launchctl bootout gui/$(id -u)/com.hadiya.server
rm -rf ~/Library/LaunchAgents/com.hadiya.server.plist ~/Applications/Hadiya.app "$HOME/Library/Application Support/Hadiya"
```
Claude Code (opcional): `rm -rf ~/.local/bin/claude ~/.local/share/claude ~/.claude`.

## Problemas frecuentes

- **No abre en `localhost:8787`**: mira el log de arriba; `launchctl print gui/$(id -u)/com.hadiya.server` indica si el servicio está cargado.
- **"Hadiya.app está dañada"**: borra la cuarentena: `xattr -dr com.apple.quarantine ~/Applications/Hadiya.app`.
- Sin voz, WhatsApp ni notificaciones push en esta versión.
