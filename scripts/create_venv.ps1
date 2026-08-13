# Kurum Yedekleme için sanal ortam oluşturma (Windows PowerShell)
# Kullanım: .\scripts\create_venv.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Proje kökü: $Root"
Write-Host "Python sürümü:"
python --version

if (Test-Path ".venv") {
    Write-Host "Mevcut .venv bulundu."
} else {
    Write-Host "Sanal ortam oluşturuluyor (.venv)..."
    python -m venv .venv
}

$pip = Join-Path $Root ".venv\Scripts\pip.exe"
$python = Join-Path $Root ".venv\Scripts\python.exe"

Write-Host "pip güncelleniyor..."
& $python -m pip install --upgrade pip

Write-Host "Bağımlılıklar kuruluyor (PySide6-Essentials + PyYAML)..."
& $pip install --no-cache-dir -r requirements.txt

Write-Host ""
Write-Host "Tamam. Etkinleştirmek için:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "Çalıştırmak için:"
Write-Host "  `$env:PYTHONPATH='src'; python -m kurum_yedekleme"
Write-Host "Duman testi:"
Write-Host "  `$env:PYTHONPATH='src'; python scripts\smoke_test.py"
