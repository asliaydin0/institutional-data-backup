# Kurum Yedekleme Windows Service kurulumu (yönetici)
# Kullanım: Yönetici PowerShell'de  .\scripts\install_service.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = (Get-Command python).Source
}

Write-Host "Proje: $Root"
Write-Host "Python: $python"

$env:PYTHONPATH = "src"
& $python -m pip install -q pywin32
& $python -c "from kurum_yedekleme.utils.sitepath import ensure_src_pth; ensure_src_pth()"
& $python -m kurum_yedekleme --install-service
if ($LASTEXITCODE -ne 0) {
    Write-Error "Servis kurulumu başarısız. Yönetici olarak çalıştırın; pywin32 kurulu olmalı."
    exit $LASTEXITCODE
}

Start-Service -Name "KurumYedekleme" -ErrorAction SilentlyContinue
sc.exe query KurumYedekleme
Write-Host "Tamam. Durdurmak: sc stop KurumYedekleme"
Write-Host "Kaldırmak: python -m kurum_yedekleme --uninstall-service"
