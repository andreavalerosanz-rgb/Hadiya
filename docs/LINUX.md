# Hadiya en Linux

> **Para quien prepara el paquete**
> 1. Ejecuta `bash scripts/build-linux.sh`.
> 2. Se crea `dist/hadiya-linux_<ver>.tar.gz` (o descárgalo de la [última release](https://github.com/andreavalerosanz-rgb/flows/releases/latest)).

Hadiya es un panel que se abre en tu ordenador para trabajar con Claude Code, con tu propia cuenta de Claude (plan de pago). Todo funciona en **esta máquina**.

## Qué necesitas

- Linux con systemd (Ubuntu, Debian, Fedora...), `python3` 3.9+ y `curl`. No hace falta root.
- Internet durante la instalación.

## Instalar

```
tar -xzf hadiya-linux_<ver>.tar.gz
cd Hadiya && ./install.sh
```

El script: instala Claude Code con el instalador oficial si falta (`~/.local/bin`), copia Hadiya a `~/.local/share/hadiya/app` (datos en `~/.local/share/hadiya`), crea el servicio de usuario `hadiya.service` (`systemctl --user`) y la entrada **Hadiya** del menú de aplicaciones, y, si hace falta, lanza `claude auth login`. Luego abre `http://localhost:8787` o usa la entrada del menú (ventana de Chrome/Chromium/Edge/Brave si hay).

Para que el servicio arranque sin tener la sesión abierta: `loginctl enable-linger $USER`.

## Actualizar

Descomprime el tar.gz nuevo y ejecuta `./install.sh` otra vez: reemplaza la aplicación, **conserva tus datos** y reinicia el servicio.

## Alternativa: paquete .deb

`scripts/build-deb.sh` genera `hadiya-dev_<ver>_all.deb` (instalación para todo el sistema en `/opt/hadiya`, servicio de usuario activado para todos). Sirve el mismo servicio y .desktop; este tar.gz es la opción sin root.

## Desinstalar

```
systemctl --user disable --now hadiya.service
rm -rf ~/.config/systemd/user/hadiya.service ~/.local/share/applications/hadiya.desktop ~/.local/share/hadiya
```
(Esto borra también tus datos.)

## Problemas frecuentes

- `systemctl --user status hadiya` y `journalctl --user -u hadiya` muestran el estado y los errores.
- "Failed to connect to bus" por SSH: usa una sesión de escritorio o `export XDG_RUNTIME_DIR=/run/user/$(id -u)`.
