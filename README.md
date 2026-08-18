# Kurum Yedekleme

Kurum birimlerinin klasörlerini ZIP olarak **yalnızca `E:\Yedekler`** altına yedekleyen Windows masaüstü uygulaması (PySide6, Türkçe).

Otomatik yedekleme **Windows Service** ile çalışır. GUI kapalı olsa ve kullanıcı oturum açmamış olsa bile servis yedek alabilir.

**Durum:** v1.0.0 — alan tabanlı yedekleme.

## Ne yapar?

- Birden fazla **yedekleme alanı** (birim/klasör): Helal Akreditasyon, Personel, Destek Hizmetleri, …
- Her alan `E:\Yedekler\<Alan>\<YYYY-MM-DD_HH-MM-SS>\<Alan>.zip` yoluna yazılır
- Manuel seçimli yedek; günlük / haftalık / aylık otomatik yedek
- İsteğe bağlı eski ZIP temizliği (saklama süresi)
- SQLite geçmişi: alan, manuel/otomatik, durum, boyut, süre
- Kaynak dosyalar yalnızca okunur; silinmez / değiştirilmez
- Yarım ZIP yalnızca `.tmp` adında kalır; başarılı olunca `.zip` olur

## Gereksinimler

| Ortam | Gereksinim |
|-------|------------|
| Son kullanıcı (EXE) | Windows 10/11, **E:** diski — Python gerekmez |
| Geliştirme | Python 3.11+, ~100+ MB disk |

## Kurulum (geliştirme)

Proje kökünde PowerShell:

```powershell
cd C:\yol\KurumYedekleme\KurumYedekleme
.\scripts\create_venv.ps1
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "src"
```

`create_venv.ps1` sanal ortamı oluşturur ve `requirements.txt` bağımlılıklarını kurar.

Her yeni terminal oturumunda `Activate.ps1` ve `PYTHONPATH` tekrar gerekir.

## Yapılandırma

1. `config/config.example.yaml` dosyasını inceleyin.
2. İlk çalıştırmada `config/config.yaml` örnekten oluşur (git’e eklenmez).
3. `backup_root` production’da `E:\Yedekler` olmalıdır.
4. Yedekleme **alanları YAML’da değil**, SQLite’dadır (`data/kurum_yedekleme.db`).
5. Parola yazmayın.

`config.yaml` özet alanları:

```yaml
schedule:
  enabled: true
  frequency: daily    # daily | weekly | monthly
  time: "02:00"
  weekday: 6          # haftalık: 0=Pazartesi … 6=Pazar
  day_of_month: 1     # aylık: 1–28

retention:
  enabled: false
  keep_days: 90
  frequency: weekly
  time: "03:00"
```

Retry ve ZIP sıkıştırma ayarları kodda varsayılan değerlerle çalışır; arayüzden değiştirilmez.

## Çalıştırma

Sanal ortam aktif ve `PYTHONPATH=src` ayarlı iken:

### Üretim GUI (E:\Yedekler, config.yaml)

```powershell
python -m kurum_yedekleme
```

Tray’de başlat (pencere gizli):

```powershell
python -m kurum_yedekleme --tray
```

### TEST MODE (yerel test, E: gerekmez)

Gerçek kurum kaynaklarına ve `E:\Yedekler` üretim klasörüne **dokunmaz**. Yedekler `tests/test_data/yedekler` altına yazılır; otomatik yedekleme pencere açıkken çalışır.

```powershell
python -m kurum_yedekleme --test-mode
```

Headless test yedeklemesi (GUI yok):

```powershell
python -m kurum_yedekleme --run-test-backup
```

### Windows Service (production otomatik yedek)

```powershell
python -m kurum_yedekleme --run-service
```

Hata ayıklama içindir; production’da kurulu Windows Service kullanın.

### Servis kurulumu (yönetici)

```powershell
python -m kurum_yedekleme --install-service
python -m kurum_yedekleme --uninstall-service
sc start KurumYedekleme
sc stop KurumYedekleme
sc query KurumYedekleme
```

veya `.\scripts\install_service.ps1`

GUI → **Ayarlar** ekranından da servis kurulumu / başlatma / durdurma yapılabilir. Ayar kaydı sonrası servisi yeniden başlatın; çalışan servis `config.yaml` değişikliğini otomatik okumaz.

## GUI kullanımı

| Ekran | İş |
|-------|-----|
| Genel Bakış | Servis durumu, bugünkü yedek, son otomatik/manuel, kaçırılmış yedek uyarısı |
| Yedekleme Alanları | Yeni alan, düzenle, aktif/pasif anahtarı, sil (soft) |
| Yedekleme | Alan seç, tümünü seç / seçimi kaldır, yedekle, iptal |
| Geçmiş | Filtre; satıra çift tıklayınca yedek ZIP klasörünü açar |
| Ayarlar | Yedekleme sıklığı, saklama, servis |
| Loglar | Dönen log dosyası |

### Yeni alan

**Yedekleme Alanları** → **Yeni Alan Ekle**

- Alan adı (benzersiz)
- Kaynak klasör (erişilebilir ve okunabilir olmalı)
- Aktif / Pasif

### Alan silme

Onay: *Bu alan uygulamadan kaldırılacak. Mevcut yedekler ve geçmiş kayıtları silinmeyecektir.*

Fiziksel ZIP’ler ve geçmiş satırları kalır (soft delete).

### Manuel yedek

**Yedekleme** ekranında alanları işaretleyin → **Seçili Alanları Yedekle**.

- **Tümünü Seç**: tüm aktif alanları işaretler; hepsi seçiliyken tekrar tıklanınca seçimi kaldırır (düğme metni **Seçimi Kaldır** olur).
- Pasif alanlar listede görünür ancak seçilemez.
- Kayıt türü: `MANUAL`.

Aynı gün ikinci manuel yedek: `Personel.zip`, `Personel_2.zip`, … (üzerine yazılmaz).

### Otomatik yedek

**Ayarlar**’da sıklık (günlük / haftalık / aylık), saat ve Windows Service’in çalışıyor olması gerekir. Tüm aktif alanlar yedeklenir. Tür: `AUTOMATIC`.

İlgili periyotta o alan için başarılı otomatik yedek varsa tekrar çalışmaz.

Planlanan saat geçmiş ve yedek alınmamışsa servis (veya TEST MODE’da açık GUI) eksik alanları yedekler.

## Yedek klasör yapısı

```
E:\Yedekler\
├── Helal Akreditasyon\
│   └── 2026-08-14_02-00-15\
│       └── Helal Akreditasyon.zip
└── Personel\
    └── 2026-08-14_14-30-00\
        ├── Personel.zip
        └── Personel_2.zip      # ikinci manuel
```

ZIP yazılırken aynı klasörde `.Personel.tmp` kullanılır; başarıda `Personel.zip` olur.

## TEST MODE

```powershell
python -m kurum_yedekleme --test-mode
python -m kurum_yedekleme --run-test-backup
```

- GUI’de kırmızı **TEST MODU** bandı görünür.
- `config.yaml` yazılmaz; ayarlar oturuma uygulanır.
- Otomatik yedekleme yalnızca pencere açıkken çalışır.
- Production’da `--test-mode` ve `KURUM_YEDEKLEME_TEST_MODE` kullanmayın.

## Loglar

Klasör: `logs/` — biçim: `Tarih Saat SEVİYE Modül İşlem - Mesaj`  
Rotasyon: `size` veya `daily`; `backup_count` ≤ 30.  
Parola / token logda `***` olur. Kaynak dosya içerikleri loglanmaz.

## Güvenlik

- Kaynaklar salt okunur (`rb`)
- Yarım dosya yalnızca `.tmp`
- Tek yedekleme kilidi (GUI + servis aynı kilit dosyası)
- Başarısız iş SUCCESS yazılmaz
- Config’de parola yok

## Testler

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "src"
$env:QT_QPA_PLATFORM = "offscreen"
$env:KURUM_YEDEKLEME_NO_TRAY = "1"
python -m pytest tests -q
```

Gerçek kurum klasörleri ve gerçek `E:\Yedekler` kullanılmaz; testler geçici dizin kullanır.

## Windows EXE

```powershell
.\build.bat
.\scripts\verify_exe.bat
```

Temiz PC: `dist\KurumYedekleme\` klasörünün **tamamını** kopyalayın. Servis kurulumu için Ayarlar veya `install_service.ps1`.

## Production kontrol listesi

1. [ ] `E:` diski var; `E:\Yedekler` yazılabilir
2. [ ] Alanlar GUI’den eklendi; kaynaklar okunabiliyor
3. [ ] TEST MODE kapalı
4. [ ] Windows Service kurulu ve **Çalışıyor** (`sc query KurumYedekleme`)
5. [ ] Yedekleme sıklığı ve saati kurum politikasına uygun
6. [ ] Küçük deneme manuel yedek SUCCESS
7. [ ] Hedefte `.tmp` yok, tarih klasöründe `.zip` var
8. [ ] Kaynak klasör değişmedi
9. [ ] Ağ kaynağı kullanılıyorsa servis hesabının okuma izni var

Ayrıntı: [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md)

## Mimari

```
Windows
  → Windows Service (KurumYedekleme)
       → Zamanlayıcı + saklama temizliği
            → Backup Manager
                 → aktif alanlar
                      → E:\Yedekler\<Alan>\<tarih_saat>\<Alan>.zip
  → GUI (isteğe bağlı)
       → alan yönetimi, manuel yedek, geçmiş, servis durumu
```

Production GUI zamanlayıcı çalıştırmaz (TEST MODE hariç). Aynı yedek işi GUI ve servisten aynı anda başlatılamaz.

## Lisans

Kurum içi kullanım — dağıtım politikasına göre güncellenecektir.

## Geliştirici 
Aslı AYDIN
