# Kurum Yedekleme

Kurum birimlerinin klasörlerini ZIP olarak **yalnızca `E:\Yedekler`** altına yedekleyen Windows masaüstü uygulaması (PySide6, Türkçe).

Otomatik yedekleme **Windows Service** ile çalışır. GUI kapalı olsa ve kullanıcı oturum açmamış olsa bile servis yedek alabilir.

**Durum:** v1.0.0 — alan tabanlı yedekleme. Bu depoda gerçek kurum verisi üzerinde işlem yapılmaz.

## Ne yapar?

- Birden fazla **yedekleme alanı** (birim/klasör): Helal Akreditasyon, Personel, Destek Hizmetleri, …
- Her alan `E:\Yedekler\<Alan>\<YYYY-MM-DD>\<Alan>.zip` yoluna yazılır
- Manuel seçimli yedek ve günlük otomatik yedek
- SQLite geçmişi: alan, manuel/otomatik, durum, boyut, süre
- Kaynak dosyalar yalnızca okunur; silinmez / değiştirilmez
- Yarım ZIP yalnızca `.tmp` adında kalır; başarılı olunca `.zip` olur

## Gereksinimler

| Ortam | Gereksinim |
|-------|------------|
| Son kullanıcı (EXE) | Windows 10/11, **E:** diski — Python gerekmez |
| Geliştirme | Python 3.11+ , ~100+ MB disk |

## Kurulum (geliştirme)

```powershell
cd <proje-kökü>
.\scripts\create_venv.ps1
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "src"
```

## Yapılandırma

1. `config/config.example.yaml` dosyasını inceleyin.
2. İlk çalıştırmada `config/config.yaml` örnekten oluşur (git’e eklenmez).
3. `backup_root` production’da `E:\Yedekler` olmalıdır.
4. Yedekleme **alanları YAML’da değil**, SQLite’dadır (`data/kurum_yedekleme.db`).
5. Parola yazmayın.

## Çalıştırma

```powershell
$env:PYTHONPATH = "src"
python -m kurum_yedekleme              # GUI
python -m kurum_yedekleme --tray       # GUI gizli, tray
python -m kurum_yedekleme --run-service
```

`--run-service` zamanlayıcıyı GUI olmadan çalıştırır (hizmet hata ayıklama). Production’da Windows Service kullanın.

## Windows Service

Otomatik yedekleme GUI’den bağımsızdır.

Yönetici PowerShell:

```powershell
.\scripts\install_service.ps1
```

veya:

```powershell
python -m kurum_yedekleme --install-service
python -m kurum_yedekleme --uninstall-service
sc start KurumYedekleme
sc stop KurumYedekleme
sc query KurumYedekleme
```

- Hizmet adı: `KurumYedekleme`
- Başlangıç: otomatik (`auto`)
- Kullanıcı oturumu gerekmez (LocalSystem). Kaynak bir ağ paylaşımıysa (`\\DosyaSunucusu\...`) bilgisayar hesabının okuma izni olmalıdır; gerekirse hizmeti yetkili bir domain hesabıyla çalıştırın.

GUI → Ayarlar’dan da servis kurulumu / başlatma / durdurma yapılabilir.

## GUI kullanımı

| Ekran | İş |
|-------|-----|
| Dashboard | Servis durumu, bugünkü yedek, son otomatik/manuel, kaçırılmış yedek uyarısı |
| Yedekleme Alanları | Yeni alan, düzenle, aktif/pasif, sil (soft), ortak alanı tara |
| Yedekleme | Alan seç, tam yedek, iptal |
| Geçmiş | Alan / tür / durum / tarih filtresi |
| Ayarlar | Saat, retry, servis |
| Loglar | Dönen log dosyası |

### Yeni alan

Yedekleme Alanları → **+ Yeni Alan Ekle**

- Alan adı (benzersiz)
- Kaynak klasör (erişilebilir ve okunabilir olmalı)
- Aktif / Pasif

### Ortak alanı tara

`\\DosyaSunucusu\OrtakAlan\` gibi bir kök seçin. Alt klasörler listelenir; istediğinizi alan olarak ekleyin. Elle alan ekleme her zaman durur.

### Alan silme

Onay: *Bu alan uygulamadan kaldırılacak. Mevcut yedekler ve geçmiş kayıtları silinmeyecektir.*

Fiziksel ZIP’ler ve geçmiş satırları kalır (soft delete).

### Manuel yedek

Yedekleme ekranında alanları işaretleyin → **Seçili Alanları Yedekle**. **Tam Yedekleme** tüm aktif alanları seçer. Kayıt türü: `MANUAL`.

Aynı gün ikinci manuel yedek: `Personel.zip`, `Personel_2.zip`, … (üzerine yazılmaz).

### Otomatik yedek

Ayarlar’da saat (ör. 02:00) ve servisin çalışıyor olması. Tüm aktif alanlar yedeklenir. Tür: `AUTOMATIC`.

Aynı gün o alan için başarılı otomatik yedek varsa tekrar çalışmaz.

Bilgisayar 02:00’da kapalıysa servis açılışında *bugünün otomatik yedeklemesi henüz yapılmadı* tespit edilir ve eksik alanlar yedeklenir.

## Yedek klasör yapısı

```
E:\Yedekler\
├── Helal Akreditasyon\
│   └── 2026-08-14\
│       └── Helal Akreditasyon.zip
└── Personel\
    └── 2026-08-14\
        ├── Personel.zip
        └── Personel_2.zip      # ikinci manuel
```

ZIP yazılırken aynı klasörde `.Personel.tmp` kullanılır; başarıda `Personel.zip` olur.

## TEST MODE

Gerçek kurum kaynaklarına ve `E:\Yedekler` üretim klasörüne **dokunmaz**.

```powershell
python -m kurum_yedekleme --test-mode
python -m kurum_yedekleme --run-test-backup
```

GUI’de kırmızı **⚠ TEST MODU AKTİF** bandı görünür. Production’da `--test-mode` ve `KURUM_YEDEKLEME_TEST_MODE` kullanmayın.

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
5. [ ] Zamanlama saati kurum politikasına uygun
6. [ ] Küçük deneme manuel yedek SUCCESS
7. [ ] Hedefte `.tmp` yok, tarih klasöründe `.zip` var
8. [ ] Kaynak klasör değişmedi
9. [ ] Ağ kaynağı kullanılıyorsa servis hesabının okuma izni var

Ayrıntı: [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md)

## Mimari

```
Windows
  → Windows Service (KurumYedekleme)
       → Scheduler
            → Backup Manager
                 → aktif alanlar
                      → E:\Yedekler\<Alan>\<tarih>\<Alan>.zip
  → GUI (isteğe bağlı)
       → alan yönetimi, manuel yedek, geçmiş, servis durumu
```

GUI zamanlayıcı çalıştırmaz. Aynı yedek işi GUI ve servisten aynı anda başlatılamaz.

## Lisans

Kurum içi kullanım — dağıtım politikasına göre güncellenecektir.
