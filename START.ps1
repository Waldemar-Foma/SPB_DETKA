param(
    [Parameter(Position=0)]
    [string]$DatasetPath = ""
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    exit 1
}

function Test-DockerEngine {
    & docker info *> $null
    return ($LASTEXITCODE -eq 0)
}

Write-Host "==============================================================="
Write-Host "  Procurement service - Docker startup"
Write-Host "==============================================================="
Write-Host ""

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker is not installed or docker.exe is not in PATH. Install Docker Desktop first."
}

if (-not (Test-DockerEngine)) {
    Write-Host "[0/5] Docker Engine is not running. Trying to start Docker Desktop..."
    $dockerDesktopCandidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
        (Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
    )
    $started = $false
    foreach ($candidate in $dockerDesktopCandidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            Start-Process -FilePath $candidate | Out-Null
            $started = $true
            break
        }
    }
    if (-not $started) {
        Fail "Docker Desktop is installed but could not be started automatically. Start it manually and run START.bat again."
    }

    for ($i = 0; $i -lt 90; $i++) {
        Start-Sleep -Seconds 2
        if (Test-DockerEngine) { break }
    }
    if (-not (Test-DockerEngine)) {
        Fail "Docker Engine did not become ready. Open Docker Desktop and wait until the engine is running."
    }
}

& docker compose version | Out-Host
if ($LASTEXITCODE -ne 0) {
    Fail "Docker Compose plugin is not available. Update Docker Desktop."
}

foreach ($dir in @("datasets", "models", "instance", "data")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot $dir) | Out-Null
}

$datasetTarget = Join-Path $PSScriptRoot "datasets\source.zip"
$datasetSource = $null

if ($DatasetPath) {
    if (-not (Test-Path -LiteralPath $DatasetPath -PathType Leaf)) {
        Fail "Dataset file was not found: $DatasetPath"
    }
    $datasetSource = (Resolve-Path -LiteralPath $DatasetPath).Path
} else {
    $parent = Split-Path -Parent $PSScriptRoot
    $candidate = Get-ChildItem -LiteralPath $parent -File -Filter "RLT.Uni_*.zip" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($candidate) {
        $datasetSource = $candidate.FullName
    }
}

if ($datasetSource) {
    $copyNeeded = $true
    if (Test-Path -LiteralPath $datasetTarget -PathType Leaf) {
        try {
            $srcInfo = Get-Item -LiteralPath $datasetSource
            $dstInfo = Get-Item -LiteralPath $datasetTarget
            if ($srcInfo.Length -eq $dstInfo.Length) { $copyNeeded = $false }
        } catch {}
    }
    if ($copyNeeded) {
        Write-Host "[1/5] Copying real dataset to datasets\source.zip ..."
        Copy-Item -LiteralPath $datasetSource -Destination $datasetTarget -Force
    } else {
        Write-Host "[1/5] Real dataset is already prepared."
    }
} elseif (Test-Path -LiteralPath $datasetTarget -PathType Leaf) {
    Write-Host "[1/5] Using datasets\source.zip."
} else {
    Write-Host "[1/5] No real dataset found. The application will use DEMO data." -ForegroundColor Yellow
    Write-Host "      Put RLT.Uni_*.zip next to the project folder or pass its path to START.bat."
}

$modelPath = Join-Path $PSScriptRoot "models\multilingual-e5-base-q4_k.gguf"
$modelPart = "$modelPath.part"
$modelUrl = "https://huggingface.co/cstr/multilingual-e5-base-GGUF/resolve/main/multilingual-e5-base-q4_k.gguf?download=true"

if (-not (Test-Path -LiteralPath $modelPath -PathType Leaf)) {
    Write-Host "[2/5] E5 model is missing. Trying to download it (~260 MB)..."
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        if (Test-Path -LiteralPath $modelPart) { Remove-Item -LiteralPath $modelPart -Force -ErrorAction SilentlyContinue }
        & curl.exe -L --fail --retry 2 --connect-timeout 20 -o $modelPart $modelUrl
        if (($LASTEXITCODE -eq 0) -and (Test-Path -LiteralPath $modelPart -PathType Leaf)) {
            Move-Item -LiteralPath $modelPart -Destination $modelPath -Force
            Write-Host "      E5 model downloaded."
        } else {
            Remove-Item -LiteralPath $modelPart -Force -ErrorAction SilentlyContinue
            Write-Host "      E5 download failed. The web app will still start with lexical fallback." -ForegroundColor Yellow
        }
    } else {
        Write-Host "      curl.exe was not found. Skipping E5 download; fallback search will be used." -ForegroundColor Yellow
    }
} else {
    Write-Host "[2/5] E5 model is already present."
}

$composeArgs = @("-f", (Join-Path $PSScriptRoot "docker-compose.yml"))
if (Test-Path -LiteralPath $modelPath -PathType Leaf) {
    $composeArgs += @("-f", (Join-Path $PSScriptRoot "docker-compose.e5.yml"))
}

Write-Host "[3/5] Building and starting containers..."
$upArgs = @("compose") + $composeArgs + @("up", "-d", "--build")
& docker @upArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] docker compose up failed." -ForegroundColor Red
    $psArgs = @("compose") + $composeArgs + @("ps")
    & docker @psArgs
    $logArgs = @("compose") + $composeArgs + @("logs", "--tail=120", "app")
    & docker @logArgs
    exit 1
}

Write-Host "[4/5] Waiting for the web application. First REAL import can take several minutes..."
$ready = $false
for ($i = 1; $i -le 750; $i++) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:5000/auth/login" -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {}

    if (($i % 15) -eq 0) {
        Write-Host "      Still starting... recent app log:"
        $logArgs = @("compose") + $composeArgs + @("logs", "--tail=8", "app")
        & docker @logArgs
    }
    Start-Sleep -Seconds 2
}

if (-not $ready) {
    Write-Host ""
    Write-Host "[ERROR] The web application did not become ready within 25 minutes." -ForegroundColor Red
    $psArgs = @("compose") + $composeArgs + @("ps")
    & docker @psArgs
    $logArgs = @("compose") + $composeArgs + @("logs", "--tail=160", "app")
    & docker @logArgs
    exit 1
}

Write-Host "[5/5] Ready. Opening http://127.0.0.1:5000/auth/login"
Start-Process "http://127.0.0.1:5000/auth/login"
Write-Host ""
Write-Host "Web:   http://127.0.0.1:5000"
Write-Host "Admin: admin@local.test / admin2026"
Write-Host ""
Write-Host "Qwen and all-minilm are prepared by Ollama on first run.
FAISS candidate search status is available in Admin."
Write-Host ""
$psArgs = @("compose") + $composeArgs + @("ps")
& docker @psArgs
exit 0
