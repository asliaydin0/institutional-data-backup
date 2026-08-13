# Kurum Yedekleme

Kurum klasörlerini ZIP olarak yedekleyip Windows UNC paylaşımına aktaran masaüstü uygulaması (PySide6, Türkçe).

**Durum:** Özellikler tamam; production öncesi yapılandırma ve kontrol listesi zorunludur. Bu depoda gerçek kurum verisi üzerinde işlem yapılmaz.

## Çalışan özellikler

- Kaynak tarama → streaming ZIP → SHA-256 → UNC aktarım (`.tmp` → doğrula → rename)
- Manuel ve zamanlanmış yedekleme; kaçırılmış yedek uyarısı
- SQLite geçmiş (SUCCESS / FAILED / CANCELLED)
- System tray, arka plan, Windows Task Scheduler ile oturum açılışı
- Kurumsal log (rotasyon + hassas alan maskeleme)
- Güvenli TEST MODE (`tests/test_data` + `test_server`)
- Windows EXE (`build.bat` → `dist\KurumYedekleme\KurumYedekleme.exe`)

## Gereksinimler

| Ortam | Gereksinim |
|-------|------------|
| Son kullanıcı (EXE) | Windows 10/11 — **Python gerekmez** |
| Geliştirme | Python 3.11+ (3.13 test edildi), ~100+ MB disk |

## Kurulum (geliştirme)

```powershell
cd <proje-kökü>
.\scripts\create_venv.ps1
.\.venv\Scripts\Activate.ps1
```

## Yapılandırma

1. `config/config.example.yaml` içindeki **PLACEHOLDER** yolları inceleyin.
2. İlk çalıştırmada `config/config.yaml` örnekten oluşur (`config.yaml` git’e eklenmez).
3. Gerçek kaynak / UNC / `temp_dir` yollarını yalnızca `config.yaml` içine yazın.
4. **Parola yazmayın** — `security.credential_target` yalnızca Credential Manager adı olabilir.

## Çalıştırma

```powershell
$env:PYTHONPATH = "src"
python -m kurum_yedekleme
python -m kurum_yedekleme --tray
```

## Windows EXE

```powershell
.\build.bat                 # release — konsol yok
.\build_debug.bat           # debug — konsol açık
.\scripts\verify_exe.bat
```

Temiz PC: `dist\KurumYedekleme\` klasörünün **tamamını** kopyalayın.

## Windows açılışında otomatik başlatma

Ayarlar → **Windows açılışında otomatik başlat** → Kaydet.

- Yalnızca Task Scheduler görevi: `KurumYedekleme\OtomatikBaslat` (`ONLOGON`, `/RL LIMITED`)
- Registry `Run` **kullanılmaz**; admin gerekmez

```powershell
schtasks /Query /TN "KurumYedekleme\OtomatikBaslat" /FO LIST /V
```

## TEST MODE

Gerçek kurum / UNC yollarına **dokunmaz**. Production’da `--test-mode` veya `KURUM_YEDEKLEME_TEST_MODE` kullanmayın.

```powershell
python -m kurum_yedekleme --run-test-backup   # → TEST_MODE_OK
python -m kurum_yedekleme --test-mode
```

## Loglar

Klasör: `logs/` — biçim: `Tarih Saat SEVİYE Modül İşlem - Mesaj`  
Rotasyon: `size` veya `daily`; `backup_count` ≤ 30.  
Parola / token logda `***` olur.

## Güvenlik ilkeleri

- Kaynaklar salt okunur (`rb`); silinmez / değiştirilmez
- Sunucuda yarım dosya yalnızca `.tmp`; hash sonrası nihai ada rename
- Tek yedekleme kilidi (`BackupInProgressError`)
- Hassas değerler config’e yazılmaz

## Testler

```powershell
$env:PYTHONPATH = "src"
$env:QT_QPA_PLATFORM = "offscreen"
$env:KURUM_YEDEKLEME_NO_TRAY = "1"
python -m pytest tests -q
```

Son koşu: **91 passed, 1 skipped** (UNC entegrasyon isteğe bağlı).

## İlk gerçek yedekleme öncesi kontrol listesi

1. [ ] `config.yaml` PLACEHOLDER değil — gerçek kaynak / UNC / temp doğrulandı
2. [ ] Temp ve hedefte yedek boyutundan fazla boş disk var
3. [ ] UNC paylaşımına yazma izni test edildi (küçük deneme klasörü)
4. [ ] `KURUM_YEDEKLEME_TEST_MODE` ortam değişkeni **yok**
5. [ ] Uygulama `--test-mode` olmadan açılıyor
6. [ ] Zamanlama saati / günleri kurum politikasına uygun
7. [ ] İlk yedek **küçük test kaynağı** ile (üretim verisinin kopyası veya dar kapsam)
8. [ ] Geçmiş’te SUCCESS + logda SHA-256 + hedefte nihai `.zip` (`.tmp` yok)
9. [ ] Kaynak klasörde dosya sayısı/boyut değişmediği doğrulandı
10. [ ] Otomatik başlatma gerekiyorsa Ayarlar’dan açıldı; `schtasks` ile kontrol edildi
11. [ ] Antivirüs EXE klasörünü engellemiyor
12. [ ] Sorumlu kişi / geri alma planı (bozuk SQLite → DB dosyasını yeniden adlandır)

Ayrıntılı denetim: [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md)

## Geliştirme durumu

| Bileşen | Durum |
|---------|--------|
| ZIP + UNC + SHA-256 | Hazır |
| SQLite geçmiş | Hazır |
| Zamanlayıcı + tray + autostart | Hazır |
| Log + TEST MODE + EXE | Hazır |
| Production yapılandırma | Operasyon ekibi — kontrol listesi |

## Lisans

Kurum içi kullanım — dağıtım politikasına göre güncellenecektir.
