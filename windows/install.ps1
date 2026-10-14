# Hadiya for Windows: per-user install into %LOCALAPPDATA%\Hadiya, no admin rights. Safe to re-run (updates the app, keeps data).
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'  # Invoke-WebRequest is 10x slower with the progress bar
$src  = Split-Path -Parent $PSScriptRoot      # the unzipped package: app files + windows\
$home_ = Join-Path $env:LOCALAPPDATA 'Hadiya'
$app  = Join-Path $home_ 'app'
$py   = Join-Path $home_ 'python'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12  # old Win10 PS 5.1
$pyVer = '3.12.10'  # last 3.12 with Windows binaries; Hadiya only needs the stdlib

Write-Host 'Instalando Hadiya...' -ForegroundColor Cyan
if ([Environment]::OSVersion.Version.Build -lt 17763) { throw 'Hace falta Windows 10 (1809) o posterior.' }
if (-not (Test-Path (Join-Path $src 'server.py'))) { throw 'Descomprime el zip completo antes de instalar (no ejecutes el instalador desde dentro del zip).' }
New-Item -ItemType Directory -Force $app, $py | Out-Null

# 1. Python (embeddable zip: private copy, touches no PATH, no installer)
if (-not (Test-Path "$py\pythonw.exe")) {
  Write-Host '1/4 Python'
  $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
  $zip = Join-Path $env:TEMP "hadiya-python.zip"
  Invoke-WebRequest "https://www.python.org/ftp/python/$pyVer/python-$pyVer-embed-$arch.zip" -OutFile $zip
  Expand-Archive $zip $py -Force; Remove-Item $zip
} else { Write-Host '1/4 Python: ya estaba' }

# 2. Claude Code (official native installer, per user, updates itself)
$claude = Join-Path $env:USERPROFILE '.local\bin\claude.exe'
if (-not (Test-Path $claude) -and -not (Get-Command claude -ErrorAction SilentlyContinue)) {
  Write-Host '2/4 Claude Code'
  # child process: the official script calls exit on errors, which would end this script under iex
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex"
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $claude)) { throw 'No se pudo instalar Claude Code.' }
} else { Write-Host '2/4 Claude Code: ya estaba' }

# 3. App files (data\ is never touched, so an update keeps sessions)
Write-Host '3/4 Hadiya'
Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq "$py\pythonw.exe" } | Stop-Process -Force
Start-Sleep -Milliseconds 500
# remove folders first: Copy-Item -Recurse into an existing folder nests it (windows\windows)
Remove-Item "$app\icons", "$app\windows" -Recurse -Force -ErrorAction SilentlyContinue
foreach ($f in 'server.py', 'VERSION', 'index.html', 'kanban.html', 'icons', 'windows') {
  Copy-Item (Join-Path $src $f) $app -Recurse -Force
}

# 4. Shortcuts: Desktop + Start menu open the app; Startup starts the server at login
Write-Host '4/4 Accesos directos'
$sh = New-Object -ComObject WScript.Shell
function Link($path, $arg) {
  $l = $sh.CreateShortcut($path)
  $l.TargetPath = "$py\pythonw.exe"; $l.Arguments = "-X utf8 `"$app\windows\hadiya.pyw`" $arg"
  $l.WorkingDirectory = $app; $l.IconLocation = "$app\windows\hadiya.ico"; $l.Description = 'Hadiya'
  $l.Save()
}
Link ([Environment]::GetFolderPath('Desktop') + '\Hadiya.lnk') ''
Link ([Environment]::GetFolderPath('Programs') + '\Hadiya.lnk') ''
Link ([Environment]::GetFolderPath('Startup') + '\Hadiya (servidor).lnk') '--server'

# First run: sign in once if `claude auth status` says not logged in (exit 1); opens the browser
$exe = if (Test-Path $claude) { $claude } else { 'claude' }
if ((Start-Process $exe 'auth', 'status' -Wait -PassThru -WindowStyle Hidden).ExitCode -ne 0) {
  Write-Host ''
  Write-Host 'Inicia sesion con tu cuenta de Claude en el navegador que se va a abrir.' -ForegroundColor Yellow
  Start-Process $exe 'auth', 'login' -Wait -NoNewWindow
}
Start-Process "$py\pythonw.exe" -ArgumentList "-X utf8 `"$app\windows\hadiya.pyw`"" -WorkingDirectory $app
Write-Host 'Listo. Hadiya esta en el escritorio y en el menu Inicio.' -ForegroundColor Green
