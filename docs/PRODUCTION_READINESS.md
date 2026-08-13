# Production Readiness Raporu

**Tarih:** 2026-08-12  
**Kapsam:** Kod incelemesi + test koşusu (gerçek kurum verisine dokunulmadı)  
**Test sonucu:** 91 passed, 1 skipped

---

## 1. Projenin mevcut durumu

Uygulama iskelet aşamasını geçmiş durumda: güvenli ZIP, UNC aktarım, SHA-256, retry, SQLite geçmiş, GUI, tray, zamanlayıcı, Task Scheduler autostart, TEST MODE ve PyInstaller EXE hazır.

Production’a geçiş **kod eksikliğinden değil**, doğru `config.yaml`, ağ izinleri ve operasyonel kontrol listesinden geçer.

---

## 2. Çalışan özellikler

| Alan | Durum |
|------|--------|
| Streaming ZIP (kaynak salt okunur) | Çalışıyor |
| `.tmp` → boyut + SHA-256 → rename | Çalışıyor |
| Retry (ağ/IO, tmp temizliği) | Çalışıyor |
| Tek job kilidi | Çalışıyor |
| SQLite geçmiş + WAL + quick_check | Çalışıyor |
| GUI (QThread) / tray / zamanlayıcı | Çalışıyor |
| Log rotasyonu + redaksiyon | Çalışıyor |
| TEST MODE / EXE build | Çalışıyor |

---

## 3. Başarısız testler

| Sonuç | Açıklama |
|-------|----------|
| 91 passed | Birim + hata senaryosu + TEST MODE + performans |
| 1 skipped | `test_transfer_unc_integration` — `\\localhost\BackupTest` yoksa atlanır |

Başarısız test **yok**.

---

## 4. Denetim maddeleri (1–20)

| # | Madde | Sonuç | Not |
|---|--------|--------|-----|
| 1 | Hard-coded şifre | **Geçti** | Yok; yalnızca `credential_target` referansı |
| 2 | Hard-coded gerçek kurum yolu | **Geçti*** | Örnekte PLACEHOLDER; yerel `config.yaml` git dışı |
| 3 | Hassas bilgi log | **Geçti** | `SensitiveDataFilter`; parola maskelenir |
| 4 | Kaynak silme/değiştirme | **Geçti** | Kaynak `rb`; unlink yalnızca `.partial` / uzak `.tmp` |
| 5 | Yarım ZIP nihai ad | **Geçti** | Nihai ad yalnızca hash sonrası `os.replace` |
| 6 | Hash doğrulama | **Geçti** | Kopyada yerel hash + uzak yeniden okuma |
| 7 | Retry güvenliği | **Geçti** | Başarısızda `.tmp` silinir; sonra yeniden deneme |
| 8 | Çift backup | **Geçti** | `acquire(blocking=False)` → `BackupInProgressError` |
| 9 | Uygulama kapanışı | **Kısmen** | Beklenmeyen hata → FAILED; ani kill → `.tmp` kalabilir (sonraki koşuda temizlenir) |
| 10 | Bilgisayar kapanışı | **Kısmen** | Aynı; nihai `.zip` hash’siz oluşmaz |
| 11 | Ağ kopması | **Geçti** | `NetworkTransferError` + retry + mesaj |
| 12 | Disk dolu | **Geçti** | ENOSPC → anlaşılır hata / FAILED |
| 13 | SQLite bozuk | **Geçti*** | `PRAGMA quick_check` + kullanıcıya DB yenileme mesajı |
| 14 | Log sınırsız büyüme | **Geçti** | Rotasyon + `backup_count` (max 30) |
| 15 | GUI thread blok | **Geçti** | `BackupWorker` QThread; progress throttle |
| 16 | Windows başlangıç | **Geçti** | Yalnızca sabit Task Scheduler adı; Run anahtarı yok |
| 17 | Config’de sır | **Geçti** | Parola alanı yok |
| 18 | TEST MODE prod’a sızma | **Risk** | `--test-mode` / env ile açılabilir — prod’da kullanmayın |
| 19 | Gereksiz dependency | **Düşük** | `PyInstaller`/`pytest` runtime için şart değil (geliştirme) |
| 20 | Exception handling | **Geçti** | Worker/engine soft-fail + kullanıcı mesajı; DB hataları dialog |

\*İyileştirildi: örnek config PLACEHOLDER; SQLite `quick_check`.

---

## 5. Düzeltilmesi gerekenler / öneriler

### Zorunlu (operasyon)

1. Production `config.yaml` — gerçek yollar, PLACEHOLDER kalmasın  
2. İlk yedek küçük/kontrollü kaynak ile  
3. Prod’da `KURUM_YEDEKLEME_TEST_MODE` ve `--test-mode` yasak

### Önerilen (kod / süreç, sonraki sprint)

1. `requirements-dev.txt` ayırımı (PyInstaller, pytest)  
2. EXE kod imzalama (SmartScreen)  
3. Ani kesintide orphan `.tmp` için periyodik temizlik görevi (hedef paylaşımda)  
4. SQLite dosyasının otomatik yedek kopyası (bozulma senaryosu)

---

## 6. Production riskleri

| Risk | Seviye | Azaltma |
|------|--------|---------|
| Yanlış config (yanlış UNC/kaynak) | Yüksek | Kontrol listesi; önce dar kapsamlı deneme |
| TEST MODE yanlışlıkla açık | Orta | Env/`--test-mode` yasak; başlıkta `[TEST MODE]` uyarısı |
| Ani güç kesintisi → orphan `.tmp` | Düşük | Nihai dosya oluşmaz; sonraki aktarım eski `.tmp` siler |
| SQLite bozulması | Düşük | quick_check; DB yeniden adlandırma prosedürü |
| 50 GB+ süre / disk | Orta | Temp+hedef boş alan; tray’de uzun iş |
| İmzasız EXE / antivirüs | Orta | Kurum istisnası veya imzalama |
| Credential Manager henüz tam entegre değil | Düşük | Parola kodda yok; UNC genelde mevcut oturum |

---

## 7. Kurulum adımları (özet)

### EXE ile

1. `dist\KurumYedekleme\` tamamını hedef PC’ye kopyala  
2. `KurumYedekleme.exe` çalıştır → `config\config.yaml` oluşur  
3. Ayarlar’dan kaynak / UNC / zaman / temp düzenle  
4. Küçük deneme yedeği → Geçmiş + hedef klasör kontrol  
5. İsteğe bağlı: otomatik başlat

### Geliştirme ortamı

```powershell
.\scripts\create_venv.ps1
$env:PYTHONPATH = "src"
python -m kurum_yedekleme
```

---

## 8. İlk gerçek yedekleme öncesi kontrol listesi

README’deki madde listesi ile aynıdır; özet:

- [ ] Config gerçek ve doğrulanmış  
- [ ] Disk alanı (temp + hedef)  
- [ ] UNC yazma izni  
- [ ] TEST MODE kapalı  
- [ ] Küçük deneme SUCCESS  
- [ ] Kaynak değişmedi  
- [ ] Hedefte `.tmp` yok, nihai `.zip` var  
- [ ] Log / geçmiş tutarlı  
- [ ] Geri alma (DB rename) biliniyor  

---

## Kod kalitesi (kısa)

- Modüler katmanlar (`core` / `services` / `ui` / `db`) net  
- Test kapsamı geniş (hata senaryoları + TEST MODE akışı)  
- Bilinçli bırakılanlar: yerel ZIP silinmez; `testzip()` maliyetli ama güvenli  
- Teknik borç: dev bağımlılıkları ayrılmamış; Credential Manager stub
