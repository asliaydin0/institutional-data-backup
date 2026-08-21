# Veri Yedekleme Sistemi — Windows Service kurulumu (yönetici)
# Kullanım:
#   Geliştirme:  Yönetici PowerShell'de  .\scripts\install_service.ps1
#   EXE:         dist\KurumYedekleme klasöründe  .\install_service.ps1
#                veya EXE yanına kopyalanmış aynı betik

$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot

function Install-FromExe([string]$ExePath) {
    $dir = Split-Path -Parent $ExePath
    Write-Host "Kurulum (EXE): $ExePath"
    Set-Location $dir
    & $ExePath --install-service
    if ($LASTEXITCODE -ne 0) {
        throw "EXE servis kurulumu başarısız. Yönetici olarak çalıştırın."
    }
}

$exeBeside = Join-Path $Here "KurumYedekleme.exe"
$repoRoot = if ((Split-Path -Leaf $Here) -eq "scripts") {
    Split-Path -Parent $Here
} else {
    $Here
}
$exeDist = Join-Path $repoRoot "dist\KurumYedekleme\KurumYedekleme.exe"

if (Test-Path $exeBeside) {
    Install-FromExe $exeBeside
}
elseif (Test-Path $exeDist) {
    Install-FromExe $exeDist
}
else {
    $Root = if ((Split-Path -Leaf $Here) -eq "scripts") {
        Split-Path -Parent $Here
    } else {
        $Here
    }
    Set-Location $Root
    $python = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        $python = (Get-Command python).Source
    }
    Write-Host "Kurulum (Python): $Root"
    Write-Host "Python: $python"
    $env:PYTHONPATH = "src"
    & $python -m pip install -q pywin32
    & $python -c "from kurum_yedekleme.utils.sitepath import ensure_src_pth; ensure_src_pth()"
    & $python -m kurum_yedekleme --install-service
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Servis kurulumu başarısız. Yönetici olarak çalıştırın; pywin32 kurulu olmalı."
        exit $LASTEXITCODE
    }
}

Start-Service -Name "KurumYedekleme" -ErrorAction SilentlyContinue
sc.exe query KurumYedekleme
Write-Host "Tamam. Durdurmak: sc stop KurumYedekleme"
Write-Host "Kaldırmak (EXE): KurumYedekleme.exe --uninstall-service"
Write-Host "Kaldırmak (venv): python -m kurum_yedekleme --uninstall-service"
