$ErrorActionPreference = "Stop"

$SourceRoot = if (Test-Path (Join-Path $PSScriptRoot "pyproject.toml")) {
    $PSScriptRoot
} else {
    Split-Path -Parent $PSScriptRoot
}
$InstallRoot = if ($env:FEEDFORGE_DEMUCS_HOME) {
    $env:FEEDFORGE_DEMUCS_HOME
} else {
    $SourceRoot
}
$Model = if ($env:FEEDFORGE_DEMUCS_MODEL) {
    $env:FEEDFORGE_DEMUCS_MODEL
} else {
    "htdemucs_6s"
}
$CacheRoot = Join-Path $InstallRoot "model-cache"
$env:TORCH_HOME = Join-Path $CacheRoot "torch"
$env:XDG_CACHE_HOME = $CacheRoot
$env:PIP_CACHE_DIR = Join-Path $InstallRoot "pip-cache"
$Venv = Join-Path $InstallRoot ".demucs-venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Marker = Join-Path $InstallRoot ".feedforge-stems-source"
$SourceStamp = "$SourceRoot|$((Get-Item (Join-Path $SourceRoot "pyproject.toml")).LastWriteTimeUtc.Ticks)"

if (-not (Test-Path $Python)) {
    New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
    python -m venv $Venv
}

if (-not (Test-Path $Marker) -or (Get-Content $Marker -Raw -ErrorAction SilentlyContinue) -ne $SourceStamp) {
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -e "$SourceRoot[stems]"
    Set-Content -Encoding UTF8 -Path $Marker -Value $SourceStamp
}
& $Python -m feedback_converter.demucs_server --host 127.0.0.1 --port 7865 --model $Model --preload-model
