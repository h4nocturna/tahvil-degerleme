# Kalite kontrol: black + ruff + mypy + pytest'i sirayla kosar.
# Kullanim:  .\kalite_kontrol.ps1            (yalnizca denetim)
#            .\kalite_kontrol.ps1 -Duzelt    (black/ruff otomatik duzeltme uygular)
param(
    [switch]$Duzelt
)

$ErrorActionPreference = "Continue"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "HATA: .venv bulunamadi. Once sanal ortami kurun:" -ForegroundColor Red
    Write-Host "  python -m venv .venv"
    Write-Host "  .venv\Scripts\python.exe -m pip install -r requirements.txt ruff black mypy"
    exit 1
}

$adimlar = @()
if ($Duzelt) {
    $adimlar += , @("black (formatla)", @("-m", "black", "."))
    $adimlar += , @("ruff (duzelt)", @("-m", "ruff", "check", "--fix", "."))
} else {
    $adimlar += , @("black (denetim)", @("-m", "black", "--check", "."))
    $adimlar += , @("ruff (denetim)", @("-m", "ruff", "check", "."))
}
$adimlar += , @("mypy (tip denetimi)", @("-m", "mypy", "bond_lab"))
$adimlar += , @("pytest (birim testleri)", @("-m", "pytest", "tests/", "-q"))

$hatali = 0
foreach ($adim in $adimlar) {
    $isim = $adim[0]
    $argumanlar = $adim[1]
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host "  $isim" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
    & $python @argumanlar
    if ($LASTEXITCODE -ne 0) {
        Write-Host "SONUC: $isim BASARISIZ (cikis kodu $LASTEXITCODE)" -ForegroundColor Red
        $hatali++
    } else {
        Write-Host "SONUC: $isim temiz gecti." -ForegroundColor Green
    }
}

Write-Host ""
if ($hatali -eq 0) {
    Write-Host "TUM KALITE KONTROLLERI GECTI." -ForegroundColor Green
    exit 0
} else {
    Write-Host "$hatali adim basarisiz. Yukaridaki ciktilari inceleyin." -ForegroundColor Red
    exit 1
}
