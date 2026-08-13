# BackupTest SMB paylaşımını oluşturur (Yönetici PowerShell gerekir)
# Hedef: \\localhost\BackupTest  →  C:\KurumYedekleme_Test\BackupTest
# Gerçek kurum sunucusu kullanılmaz.

$ErrorActionPreference = "Stop"
$ShareName = "BackupTest"
$SharePath = "C:\KurumYedekleme_Test\BackupTest"

New-Item -ItemType Directory -Force -Path $SharePath | Out-Null

$existing = Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Paylaşım zaten var: \\localhost\$ShareName -> $($existing.Path)"
} else {
    New-SmbShare -Name $ShareName -Path $SharePath -FullAccess "Everyone"
    Write-Host "Paylaşım oluşturuldu: \\localhost\$ShareName -> $SharePath"
}

if (Test-Path "\\localhost\$ShareName") {
    Write-Host "UNC erişimi OK: \\localhost\$ShareName"
    exit 0
} else {
    Write-Host "UNC yolu henüz görünmüyor. Birkaç saniye bekleyip tekrar deneyin."
    exit 1
}
