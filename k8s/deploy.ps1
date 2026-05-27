<#
.SYNOPSIS
    deployment systemu Weather & AQI na klaster kind.

.DESCRIPTION
    kolejnosc krokow:
      1. weryfikacja narzedzi (kind, kubectl, docker)
      2. tworzenie klastra kind (jesli nie istnieje)
      3. build obrazow Docker (target: prod)
      4. ladowanie obrazow do klastra (kind load)
      5. aplikowanie manifestow k8s
      6. oczekiwanie na gotowosc deploymentow
      7. wyswietlenie statusu i URL

.EXAMPLE
    # pelny deployment od zera:
    .\k8s\deploy.ps1

    # tylko aktualizacja obrazow (klaster juz istnieje):
    .\k8s\deploy.ps1 -SkipClusterCreate

    # usuniecie klastra:
    .\k8s\deploy.ps1 -Destroy

.NOTES
    wymagania: Docker Desktop, kind, kubectl
    czas deploymentu: ~3-5 min (pierwsze uruchomienie)
#>

[CmdletBinding()]
param(
    [switch]$SkipClusterCreate,
    [switch]$Destroy
)

$ErrorActionPreference = "Stop"
$ClusterName = "weather-prod"
$Namespace   = "weather-prod"
$RootDir     = Split-Path $PSScriptRoot -Parent

function Write-Step  { param($msg) Write-Host "`n[STEP] $msg" -ForegroundColor Cyan }
function Write-OK    { param($msg) Write-Host "  [OK] $msg"   -ForegroundColor Green }
function Write-Fail  { param($msg) Write-Host " [ERR] $msg"   -ForegroundColor Red; exit 1 }
function Write-Info  { param($msg) Write-Host "  [-]  $msg"   -ForegroundColor Yellow }

if ($Destroy) {
    Write-Step "usuwanie klastra kind '$ClusterName'..."
    kind delete cluster --name $ClusterName
    Write-OK "klaster usuniety."
    exit 0
}

# weryfikacja wymaganych narzedzi
Write-Step "weryfikacja wymagan..."
foreach ($tool in @("docker", "kind", "kubectl")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Fail "'$tool' nie znaleziony w PATH. zainstaluj i uruchom ponownie."
    }
    Write-OK "$tool dostepny"
}

# tworzenie klastra
if (-not $SkipClusterCreate) {
    Write-Step "sprawdzanie klastra kind '$ClusterName'..."

    $existingClusters = @()
    # pobieramy klastry przez cmd, unikamy przechwytywania bledow powershella
    $existingClusters = @(cmd.exe /c "kind get clusters 2>nul")

    if ($existingClusters -contains $ClusterName) {
        Write-Info "klaster '$ClusterName' juz istnieje - pomijam tworzenie."
        Write-Info "uzyj -SkipClusterCreate aby wymusic pominięcie lub -Destroy aby usunac."
    } else {
        Write-Info "tworzenie klastra (moze potrwac ~2 minuty)..."
        kind create cluster --config "$PSScriptRoot\kind-config.yml"
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "nie udalo sie utworzyc klastra kind. upewnij sie, ze porty 8000 i 8080 nie sa zajete (zatrzymaj dev: docker compose -f docker-compose.dev.yml down)."
        }
        Write-OK "klaster '$ClusterName' utworzony."
    }
} else {
    Write-Info "pomijanie tworzenia klastra (-SkipClusterCreate)."
}

# budowanie obrazow docker
Write-Step "budowanie obrazow Docker (target: prod)..."

$images = @(
    @{ Tag = "weather-aqi-db:prod";       Context = "$RootDir\database" },
    @{ Tag = "weather-aqi-backend:prod";   Context = "$RootDir\backend";   Target = "prod" },
    @{ Tag = "weather-aqi-ingestion:prod"; Context = "$RootDir\ingestion"; Target = "prod" },
    @{ Tag = "weather-aqi-frontend:prod";  Context = "$RootDir\frontend";  Target = "prod" }
)

foreach ($img in $images) {
    Write-Info "budowanie: $($img.Tag)..."
    if ($img.Target) {
        docker build --target $img.Target -t $img.Tag $img.Context
    } else {
        docker build -t $img.Tag $img.Context
    }
    if ($LASTEXITCODE -ne 0) { Write-Fail "build obrazu $($img.Tag) nie powiodl sie." }
    Write-OK "zbudowano: $($img.Tag)"
}

# ladowanie obrazow do kind
Write-Step "ladowanie obrazow do klastra kind..."
foreach ($img in $images) {
    Write-Info "ladowanie: $($img.Tag)..."
    kind load docker-image $img.Tag --name $ClusterName
    if ($LASTEXITCODE -ne 0) { Write-Fail "nie udalo sie zaladowac obrazu $($img.Tag) do kind." }
    Write-OK "zaladowano: $($img.Tag)"
}

# aplikowanie manifestow k8s
Write-Step "aplikowanie manifestow Kubernetes..."

$manifests = @(
    "$PSScriptRoot\namespace.yml",
    "$PSScriptRoot\configmap.yml",
    "$PSScriptRoot\secret.yml",
    "$PSScriptRoot\db\pvc.yml",
    "$PSScriptRoot\db\deployment.yml",
    "$PSScriptRoot\db\service.yml",
    "$PSScriptRoot\backend\deployment.yml",
    "$PSScriptRoot\backend\service.yml",
    "$PSScriptRoot\ingestion\deployment.yml",
    "$PSScriptRoot\frontend\deployment.yml",
    "$PSScriptRoot\frontend\service.yml"
)

foreach ($manifest in $manifests) {
    $filename = Split-Path $manifest -Leaf
    kubectl apply -f $manifest
    if ($LASTEXITCODE -ne 0) { Write-Fail "blad aplikowania manifestu: $filename" }
    Write-OK "zastosowano: $filename"
}

# oczekiwanie na gotowosc podow
Write-Step "oczekiwanie na gotowosc wszystkich komponentow (timeout: 5 min)..."

$deployments = @("db", "backend", "frontend", "ingestion")
foreach ($dep in $deployments) {
    Write-Info "czekam na '$dep'..."
    kubectl rollout status deployment/$dep -n $Namespace --timeout=300s
    if ($LASTEXITCODE -ne 0) {
        Write-Info "szczegoly bledu:"
        kubectl describe deployment/$dep -n $Namespace
        kubectl get pods -n $Namespace -l "app=$dep"
        Write-Fail "deployment '$dep' nie osiegnal stanu Ready w ciagu 5 minut."
    }
    Write-OK "$dep gotowy."
}

# koncowy status wdrozenia
Write-Step "status systemu:"
kubectl get pods,services -n $Namespace

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  DEPLOYMENT ZAKONCZONY SUKCESEM" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Frontend UI:  http://localhost:8080" -ForegroundColor White
Write-Host "  Backend API:  http://localhost:8000" -ForegroundColor White
Write-Host "  Swagger UI:   http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "  logi: kubectl logs -n $Namespace deployment/<nazwa>" -ForegroundColor Gray
Write-Host "  usuniecie: .\k8s\deploy.ps1 -Destroy" -ForegroundColor Gray
Write-Host ""
