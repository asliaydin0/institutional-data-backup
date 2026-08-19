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

Write-Host "Bağımlılıklar kuruluyor..."
& $pip install --no-cache-dir -r requirements.txt

Write-Host "Paket src yolu venv'e bağlanıyor (servis import'u için)..."
$src = Join-Path $Root "src"
$pth = Join-Path $Root ".venv\Lib\site-packages\kurum_yedekleme_src.pth"
Set-Content -Path $pth -Value $src -Encoding utf8
& $pip install -e .

Write-Host ""
Write-Host "Tamam. Etkinleştirmek için:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "Çalıştırmak için:"
Write-Host "  python -m kurum_yedekleme --test-mode"
Write-Host "Duman testi:"
Write-Host "  python scripts\smoke_test.py"
