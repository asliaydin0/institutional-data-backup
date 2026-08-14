# Production Readiness

**Tarih:** 2026-08-14  
**Sürüm:** 1.0.0  
**Kapsam:** Alan tabanlı yedekleme, E:\Yedekler, Windows Service

## Mimari

GUI ve Windows Service aynı `BackupManager` kodunu kullanır. Otomatik zamanlama yalnızca serviste çalışır.

Yedek kökü production’da `E:\Yedekler`. TEST MODE `tests/test_data/yedekler` kullanır.

## Kaldırılan özellikler

UNC aktarım, SHA-256, Credential Manager, Task Scheduler autostart, yerel temp ZIP klasörü.

## Production kontrol listesi

README’deki madde listesi geçerlidir.

Özellikle:

- Servis `KurumYedekleme` otomatik başlar
- Kaynak UNC ise LocalSystem yerine domain hesabı gerekebilir
- EXE kod imzası / antivirüs istisnası kurum politikasına bağlıdır
- SQLite bozulursa `data/kurum_yedekleme.db` yeniden adlandırılır; uygulama yeni DB açar (geçmiş kaybolur — dosyayı saklayın)

## Geri alma

Eski şema (v2) açılışta v3’e migrate edilir. Eski history satırları `area_name` + `MANUAL` olarak korunur; SHA sütunu kalkar.
