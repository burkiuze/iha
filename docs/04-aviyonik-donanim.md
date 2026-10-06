# 04 — Aviyonik Donanım Mimarisi

## 1. Felsefe: farklı mimarili (dissimilar) üçlü artıklık

Klasik "üç aynı kart" yaklaşımı rastgele donanım arızasına karşı korur ama
**ortak mod** hatasına (aynı derleyici hatası, aynı silikon errata'sı,
aynı yazılım hatası) karşı korumaz. SİMURG'da üç şerit bilinçli olarak
farklıdır:

| | Şerit A — "Komuta" | Şerit B — "Komuta" | Şerit C — "Monitör" |
|---|---|---|---|
| İşlemci | ARM Cortex-R52, kilit adımlı (lockstep) çekirdek çifti | RISC-V, kilit adımlı | FPGA (yumuşak çekirdek yok, saf mantık) |
| İşletim sistemi | ARINC 653 uyumlu bölümlemeli RTOS | Farklı tedarikçili, mikroçekirdek RTOS | Yok (donanım durum makinesi) |
| Dil | C (MISRA C:2012) | Rust (`no_std`, `#![forbid(unsafe_code)]` uygulama katmanında) | VHDL |
| Ekip | Ekip-1 | Ekip-2 (A'nın kodunu görmez) | Ekip-3 |
| Görev | Tam uçuş kontrolü | Tam uçuş kontrolü | Zarf denetimi, oylama, FTS tetik ön koşulu |
| IMU | Tedarikçi-X MEMS | Tedarikçi-Y MEMS | Taktik sınıf MEMS (FOG yerine) |

A ve B aynı gereksinimden bağımsız olarak geliştirilir (N-versiyon
programlama). C, A ve B'nin çıkışlarını karşılaştırır ve yalnızca basit,
biçimsel olarak doğrulanmış kurallar uygular.

### 1.1 Komuta-monitör çalışma
```mermaid
sequenceDiagram
  participant A as Şerit A
  participant B as Şerit B
  participant C as Şerit C (FPGA)
  participant ESC as ESC'ler
  A->>C: u_A, durum_A, CRC (her 4 ms)
  B->>C: u_B, durum_B, CRC
  C->>C: |u_A − u_B| < tol ? sağlık bayrakları ?
  alt uyumlu
    C->>ESC: aktif şeridin komutu (A), imzalı çerçeve
  else A tutarsız / sessiz
    C->>ESC: B'ye geçiş (≤ 1 çevrim)
  else A ve B tutarsız, kim haklı belirsiz
    C->>C: IMU-C ile 3. oy; azınlık yalıtılır
  else ikisi de kayıp
    C->>ESC: "güvenli hover/süzülme" sabit yasası + FTS hazır
  end
```

Oylama mantığının referans modeli: `simurg/fdir/monitor.py::TripleLaneVoter`.

## 2. Ağ mimarisi

| Ağ | Teknoloji | Kullanım |
|---|---|---|
| Uçuş-kritik omurga | **TSN** (IEEE 802.1Qbv zaman tetiklemeli + 802.1CB çerçeve çoğaltma), 100BASE-T1, çift yıldız (X ve Y anahtarı) | FCC ↔ FCC, FCC ↔ sensör/ESC ağ geçitleri |
| Motor yedek yolu | 2 × CAN-FD (DroneCAN), A ve B | ESC'lere doğrudan; TSN tamamen kaybolursa |
| Görev ağı | 1000BASE-T1 | Görev bilgisayarı, kameralar, görev bölmesi |
| Bakım | USB-C (yalnızca yerde, kilitli) | Kayıt indirme, imzalı yazılım yükleme |

**802.1CB** sayesinde her uçuş-kritik çerçeve iki bağımsız yoldan (X ve Y
anahtarları) gönderilir; alıcı ilk geleni kabul eder, kopyayı atar. Tek
anahtar veya kablo kaybı **sıfır paket kaybı** ile tolere edilir.

Zaman tetiklemeli çizelge (4 ms ana çevrim, 250 Hz):

| Dilim (µs) | Trafik |
|---|---|
| 0–400 | IMU'lar → FCC (1 kHz örnek, 4'lü paket) |
| 400–800 | ESC telemetrisi → FCC |
| 800–1600 | FCC A/B hesap penceresi (ağ boş) |
| 1600–2000 | FCC → Monitör (komut + durum) |
| 2000–2400 | Monitör → ESC/servo (onaylı komut) |
| 2400–4000 | Tahmin edilebilir en iyi çaba trafiği (nav, görev) |

## 3. Sensör seti

| Sensör | Adet | Not |
|---|---|---|
| IMU (MEMS, 3 farklı tedarikçi) | 3 | Her şeritte bir; titreşim izolasyonlu |
| Hava verisi (pitot-statik) | 3 | Her iki kanat ucunda + gövdede; askıda devre dışı |
| Hücum açısı / yan kayma (5 delikli prob) | 1 | Geçiş koridoru kontrolü için kritik |
| Barometre | 3 | |
| GNSS (çok bantlı, çok takımyıldızlı, CRPA anten) | 2 | Galileo OSNMA kimlik doğrulama |
| Manyetometre dizisi | 4 | Gövde ucunda, motorlardan uzak; MagNav için |
| Görsel kameralar (küresel enstantane) | 3 | Aşağı, ileri, yukarı (yıldız/güneş) |
| LiDAR altimetre | 1 | 0–150 m, iniş ve TRN |
| Radar altimetre (FMCW 60 GHz) | 1 | Sis/toz/duman altında iniş |
| ADS-B In + FLARM | 1 | Algıla-ve-kaçın |
| Akustik dizi (4 mikrofon) | 1 | Transponder'sız hava araçlarını yön tayini (DAA) |

## 4. Görev bilgisayarı

- Gömülü GPU'lu modül (~100 TOPS sınıfı), **uçuş-kritik değildir**.
- Görev: algılama (termal anomali, duman, yapısal hasar), VIO, TRN harita eşleme, görev
  planlama, sürü yazılımı.
- FCC'lere yalnızca **öneri** (setpoint, rota) gönderir; bu öneriler
  RTA'dan geçer. Görev bilgisayarı tamamen çökse bile araç güvenli uçar.

## 5. Görev bölmesi (sıcak değiştirilebilir)

| Özellik | Değer |
|---|---|
| Mekanik | Tek elle takılan ray + yaylı kilit; kör geçmeli konnektör |
| Güç | 48 V, 120 W sürekli / 250 W tepe, akım sınırlı e-sigorta |
| Veri | 1 GbE + 2 × CAN-FD + PPS zaman sinyali |
| Kimlik | Bölme içindeki EEPROM'da **imzalı elektronik veri sayfası**: kütle, AM, güç profili, veri şeması, sürükleme artışı |

Takıldığında FCC veri sayfasını okur, imzayı doğrular, kütle/AM'yi uçuş
kontrol modeline, güç profilini enerji yöneticisine, sürükleme artışını
performans modeline otomatik işler. İmza geçersizse bölme **güçlendirilmez**.

Örnek bölmeler: EO/IR gözlem kamerası (afet ve hasar tespiti), çok
spektrumlu kamera (çevre izleme), gaz algılayıcı "burun" (yangın/sızıntı
izleme), LTE/mesh haberleşme röle istasyonu. Yük bırakma mekanizması
kapsam dışıdır.

## 6. Uçuş sonlandırma sistemi (FTS)

- Ayrı mikrodenetleyici, ayrı alıcı (ayrı frekans), ayrı batarya.
- Tetikleyiciler: (a) operatörden şifreli FTS komutu, (b) sert geofence
  ihlali + monitör onayı, (c) tüm FCC şeritlerinin kaybı + 2 s.
- Eylem: motor gücünü keser (ESC enable hattı), H₂ solenoidini kapatır,
  balistik paraşütü ateşler.
