# Hadiya en Windows

> **Para quien prepara el paquete**
> 1. Ejecuta `bash scripts/build-win.sh`.
> 2. Se crea `dist/hadiya-windows_<ver>.zip`.
> 3. Envía ese zip a la persona. Nada más.

Hadiya es un panel que se abre en tu ordenador para trabajar con Claude Code: preparas tareas, las lanzas y ves en directo lo que hace cada agente. Todo funciona en **este PC**: los archivos que Hadiya toque son los de este ordenador, y usa tu propia cuenta de Claude.

## Qué necesitas

- Windows 10 (versión 1809 o más nueva) o Windows 11.
- Conexión a internet durante la instalación.
- Una cuenta de Claude con plan de pago (Pro, Max o similar).
- No hace falta ser administrador.

## Instalar

1. Descarga el archivo `hadiya-windows_<ver>.zip` que te han enviado.
2. Haz clic derecho sobre el zip y elige **Extraer todo...**. Verás una carpeta llamada `Hadiya`.
3. Abre esa carpeta y haz doble clic en **Instalar Hadiya.cmd**.
4. Si Windows muestra "Windows protegió su PC", pulsa **Más información** y luego **Ejecutar de todas formas**. Sale porque los archivos no llevan firma digital; es normal.
5. Espera unos minutos. Se abre una ventana negra con texto: es el instalador. Descarga lo que falta (una copia privada de Python y Claude Code) y no toca nada más de tu sistema.
6. Cuando se abra Claude Code, inicia sesión (mira "Primer uso") y cierra esa ventana.
7. Se abre Hadiya en su propia ventana. Ya está.

El instalador deja Hadiya en `%LOCALAPPDATA%\Hadiya` y crea un acceso **Hadiya** en el Escritorio y en el menú Inicio.

## Primer uso

La primera vez, Claude Code te pide entrar en tu cuenta:

1. Se abre el navegador con la página de Claude.
2. Entra con tu cuenta y acepta.
3. Vuelve a la ventana negra, ciérrala, y Hadiya se abrirá solo.

Esto se hace una sola vez.

## Uso diario

- Haz doble clic en **Hadiya** (Escritorio o menú Inicio). Se abre en una ventana de Edge.
- Hadiya arranca solo en segundo plano cuando enciendes el PC (hay un acceso "Hadiya (servidor)" en la carpeta de Inicio de Windows), así que normalmente ya está listo.
- Tus tareas y sesiones se guardan en `%LOCALAPPDATA%\Hadiya\app\data`.

## Actualizar

1. Extrae el zip nuevo.
2. Haz doble clic en **Instalar Hadiya.cmd** otra vez.

Se actualiza la aplicación y **se conservan tus datos**.

## Desinstalar

1. Borra la carpeta `%LOCALAPPDATA%\Hadiya` (pégalo en la barra de direcciones del Explorador).
2. Borra los tres accesos: **Hadiya** en el Escritorio, **Hadiya** en el menú Inicio y **Hadiya (servidor)** en la carpeta Inicio (`Win + R`, escribe `shell:startup`).
3. Si también quieres quitar Claude Code: borra `%USERPROFILE%\.local\bin\claude.exe` y la carpeta `%USERPROFILE%\.claude`.

## Problemas frecuentes

**La página no se abre o sale en blanco.**
Cierra la ventana y abre **Hadiya** otra vez. Si sigue igual, mira el archivo `%LOCALAPPDATA%\Hadiya\app\data\server.log` y envíaselo a quien te dio el paquete.

**Dice "Claude no ha iniciado sesión".**
Abre el menú Inicio, escribe `PowerShell`, ábrelo, escribe `claude auth login` y pulsa Intro. Inicia sesión y vuelve a Hadiya.

**El antivirus bloquea la instalación.**
Los archivos no están firmados, y algunos antivirus desconfían. Permite la carpeta `Hadiya` o el instalador y vuelve a ejecutarlo.

**El puerto 8787 está ocupado.**
Hadiya usa la dirección `http://localhost:8787`. Si otro programa la usa, ciérralo, o reinicia el PC y abre Hadiya antes que nada.

**Esto no funciona en Windows (por ahora).**
La transcripción de voz, el asistente por WhatsApp y los avisos al móvil no están disponibles en la versión de Windows. La automatización del navegador (Playwright) necesita instalar Node.js aparte: abre PowerShell y ejecuta `winget install OpenJS.NodeJS.LTS`.
