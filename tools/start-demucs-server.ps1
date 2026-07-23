$ErrorActionPreference = "Stop"

function Invoke-FeedForgeNative {
    param(
        [Parameter(Mandatory = $true)]
        [string] $FilePath,
        [string[]] $Arguments = @()
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $FilePath $($Arguments -join ' ')"
    }
}

function Test-FeedForgeStorePythonAlias {
    param([string] $FilePath)
    return $FilePath -match "\\Microsoft\\WindowsApps\\python(3)?\.exe$"
}

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
$Device = if ($env:FEEDFORGE_DEMUCS_DEVICE) {
    $env:FEEDFORGE_DEMUCS_DEVICE
} else {
    "auto"
}
$Concurrency = if ($env:FEEDFORGE_DEMUCS_CONCURRENCY) {
    $env:FEEDFORGE_DEMUCS_CONCURRENCY
} else {
    "1"
}
$CacheRoot = Join-Path $InstallRoot "model-cache"
$RuntimeRoot = Join-Path $InstallRoot "runtime"
$TempRoot = Join-Path $RuntimeRoot "temp"
$StorageRoot = Join-Path $RuntimeRoot "jobs"
New-Item -ItemType Directory -Force -Path $CacheRoot, $TempRoot, $StorageRoot | Out-Null
$env:TORCH_HOME = Join-Path $CacheRoot "torch"
$env:XDG_CACHE_HOME = $CacheRoot
$env:PIP_CACHE_DIR = Join-Path $InstallRoot "pip-cache"
$env:HF_HOME = Join-Path $CacheRoot "huggingface"
$env:TEMP = $TempRoot
$env:TMP = $TempRoot
$TorchIndex = if ($env:FEEDFORGE_TORCH_INDEX) {
    $env:FEEDFORGE_TORCH_INDEX
} else {
    ""
}
if ($TorchIndex -eq "auto") {
    $HasNvidiaSmi = $false
    try {
        $null = Get-Command nvidia-smi.exe -ErrorAction Stop
        $HasNvidiaSmi = $true
    } catch {
        $HasNvidiaSmi = $false
    }
    $TorchIndex = if ($HasNvidiaSmi) { "https://download.pytorch.org/whl/cu128" } else { "" }
}
$Venv = Join-Path $InstallRoot ".demucs-venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$SystemPython = $null
if ($env:FEEDFORGE_PYTHON_EXE -and (Test-Path $env:FEEDFORGE_PYTHON_EXE)) {
    $SystemPython = $env:FEEDFORGE_PYTHON_EXE
} else {
    try {
        $SystemPython = (Get-Command python.exe -ErrorAction Stop).Source
        if (Test-FeedForgeStorePythonAlias $SystemPython) {
            $SystemPython = $null
            throw "Ignoring Microsoft Store Python alias"
        }
    } catch {
        try {
            $SystemPython = (Get-Command py.exe -ErrorAction Stop).Source
        } catch {
            $SystemPython = $null
        }
    }
}
$Marker = Join-Path $InstallRoot ".feedforge-stems-source"
$SourceStamp = "$SourceRoot|$((Get-Item (Join-Path $SourceRoot "pyproject.toml")).LastWriteTimeUtc.Ticks)|torch=$TorchIndex"

Write-Host "FeedForge: preparing local stem setup"
Write-Host "FeedForge: install folder $InstallRoot"
Write-Host "FeedForge: runtime folder $RuntimeRoot"
Write-Host "FeedForge: selected model $Model"
Write-Host "FeedForge: selected device $Device"

if (-not (Test-Path $Python)) {
    if (-not $SystemPython) {
        Write-Error "Python 3.11 or newer was not found. Install Python from https://www.python.org/downloads/windows/ and enable 'Add python.exe to PATH', then start the local stem server again."
        exit 2
    }
    New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
    Write-Host "FeedForge: creating local Python environment"
    Write-Host "FeedForge: source Python $SystemPython"
    if ((Split-Path -Leaf $SystemPython) -ieq "py.exe") {
        Invoke-FeedForgeNative $SystemPython @("-3", "-m", "venv", $Venv)
    } else {
        Invoke-FeedForgeNative $SystemPython @("-m", "venv", $Venv)
    }
} else {
    Write-Host "FeedForge: reusing local Python environment"
}

if (-not (Test-Path $Marker) -or (Get-Content $Marker -Raw -ErrorAction SilentlyContinue) -ne $SourceStamp) {
    Write-Host "FeedForge: installing FeedForge stem dependencies"
    Invoke-FeedForgeNative $Python @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-FeedForgeNative $Python @("-m", "pip", "install", "-e", "$SourceRoot[stems]")
    if ($TorchIndex) {
        $TorchReady = $false
        try {
            Invoke-FeedForgeNative $Python @("-c", "import torch, sys; sys.exit(0 if getattr(torch.version, 'cuda', None) else 1)")
            $TorchReady = $true
        } catch {
            $TorchReady = $false
        }
        if ($TorchReady) {
            Write-Host "FeedForge: CUDA PyTorch runtime already installed"
        } else {
            Write-Host "FeedForge: installing CUDA PyTorch runtime"
            Invoke-FeedForgeNative $Python @("-m", "pip", "install", "--upgrade", "torch", "torchvision", "torchaudio", "--index-url", $TorchIndex)
        }
    }
    Set-Content -Encoding UTF8 -Path $Marker -Value $SourceStamp
} else {
    Write-Host "FeedForge: dependencies already installed"
}
Write-Host "FeedForge: verifying Demucs runtime"
try {
    Invoke-FeedForgeNative $Python @("-c", "import demucs, fastapi, soundfile, torch")
} catch {
    Write-Host "FeedForge: repairing missing stem dependencies"
    Invoke-FeedForgeNative $Python @("-m", "pip", "install", "-e", "$SourceRoot[stems]")
    Invoke-FeedForgeNative $Python @("-c", "import demucs, fastapi, soundfile, torch")
    Set-Content -Encoding UTF8 -Path $Marker -Value $SourceStamp
}
Write-Host "FeedForge: starting Demucs server"
Write-Host "FeedForge: loading selected model. First launch may download model files and can take several minutes."
& $Python @("-m", "feedback_converter.demucs_server", "--host", "127.0.0.1", "--port", "7865", "--model", $Model, "--device", $Device, "--concurrency", $Concurrency, "--storage-dir", $StorageRoot, "--preload-model")
$ServerExitCode = $LASTEXITCODE
if ($ServerExitCode -ne 0) {
    Write-Host "FeedForge: local stem server failed while loading model '$Model' on device '$Device'."
    Write-Host "FeedForge: open Diagnostics -> Open log and send the full log if this continues."
    exit $ServerExitCode
}
