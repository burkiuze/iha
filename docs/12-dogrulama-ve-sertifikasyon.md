# 12 — Doğrulama, Test ve Sertifikasyon

## 1. Test piramidi

```
                       ┌──────────────┐
                       │ Uçuş testleri│  aşamalı zarf genişletme
                     ┌─┴──────────────┴─┐
                     │ Demir kuş (iron  │  gerçek aviyonik + gerçek
                     │ bird) / HIL      │  eyleyiciler + simüle aerodinamik
                   ┌─┴──────────────────┴─┐
                   │ SIL: uçuş kodu + 6-DOF│  binlerce Monte Carlo koşusu
                 ┌─┴──────────────────────┴─┐
                 │ Back-to-back: uçuş kodu   │  A (C) ve B (Rust) ↔ altın model
                 │ ↔ altın model (bu depo)   │
               ┌─┴──────────────────────────┴─┐
               │ Birim testleri (altın model:  │  `python3 -m unittest`
               │ tests/, uçuş kodu: her şerit) │
               └──────────────────────────────┘
```

### 1.1 Bu depodaki doğrulama
`tests/` altındaki her test bir veya daha fazla gereksinime izlenir
(bkz. [01-gereksinimler.md](01-gereksinimler.md) "Kod" sütunu). Yeni bir
gereksinim testi olmadan "tamamlandı" sayılmaz.

### 1.2 Monte Carlo SIL kampanyası (plan)
Her sürüm için ≥ 10 000 koşu, rastgele değişkenler:
- Rüzgâr (ortalama 0–15 m/s, Dryden türbülansı, hamleler),
- Kütle ±%10, AM ±2 cm,
- Sensör gürültüsü/sapma, IMU şerit arızası,
- Rastgele zamanda 0–2 motor arızası, kısmi pervane hasarı,
- GNSS kaybı / sahteciliği, C2 kaybı,
- Batarya kapasitesi −%20, FC bozunumu.

Kabul ölçütleri: kontrol kaybı olasılığı < 1e−4 / koşu (SIL istatistiği,
analizle birleştirilerek), acil durum kararlarının %100'ü tablodaki
önceliğe uygun, RTA anahtarlamasında hiçbir sert zarf ihlali.

## 2. Biçimsel yöntemler

| Bileşen | Yöntem | Kanıtlanacak özellik |
|---|---|---|
| Mod makinesi | Model denetimi (TLA+ veya eşdeğeri) | Tablo dışı geçiş yok; havadayken DISARMED'a ulaşılamaz; PARACHUTE sonrası geri dönüş yok |
| RTA karar mantığı | SMT tabanlı doğrulama | Sert ihlal ⇒ kilit; kilitliyken AC çıktısı asla seçilmez |
| Şerit oylayıcı (FPGA) | Eşdeğerlik denetimi + özellik doğrulama | Tek şerit hatası çıktıya yansımaz |
| Kontrol dağıtıcı | Soyut yorumlama (sınır analizi) | Çıktılar her zaman eyleyici sınırları içinde; döngü n+1'de biter |
| Rust şeridi | Tip sistemi + `forbid(unsafe)` + Kani benzeri sınırlı model denetimi | Panik yok, taşma yok |

## 3. Standartlar ve düzenleyici çerçeve

| Alan | Referans | SİMURG yaklaşımı |
|---|---|---|
| Operasyon kategorisi | EASA "spesifik" kategori, **SORA** (Specific Operations Risk Assessment); Türkiye'de SHGM İHA talimatı | Kırsal/afet bölgesi, BVLOS: hedef SAIL III–IV |
| Yazılım güvencesi | DO-178C (kavramsal eşleme) | P0, P1, P3 → DAL-B; P2, P4 → DAL-C; P5 → DAL-D; görev bilgisayarı → DAL-E |
| Donanım güvencesi | DO-254 | Şerit C FPGA → DAL-B |
| Güvenlik analizi | ARP4761 süreçleri | FHA → PSSA → SSA; FMEA, FTA |
| Çevresel | DO-160 seçili bölümler | Sıcaklık, titreşim, nem, EMI/EMC, yıldırım dolaylı etki (azaltılmış) |
| Remote ID | ASTM F3411 | Yayın tipi |
| DAA | ASTM F3442 (küçük İHA'lar için DAA performansı) | Hedef: işbirlikçi + işbirlikçi olmayan |
| Paraşüt | ASTM F3322 | Balistik sistem |
| Hidrojen | Tip-IV kap standartları, yerde ATEX bölge sınıflandırması | |

### 3.1 SORA'ya katkı sağlayan tasarım özellikleri

| SORA unsuru | Tasarım katkısı |
|---|---|
| M1 (yerdeki riskin azaltılması — stratejik) | Görev planında nüfus yoğunluğu haritası, sanal prova |
| M2 (yere çarpma etkisinin azaltılması) | Balistik paraşüt (≤ 5 m/s iniş), FTS |
| OSO: teknik sorunlarda güvenli kurtarma | Tek motor arızası toleransı, farklı mimarili üçlü FCC, RTA |
| OSO: dış sistemlerin bozulması (C2, GNSS) | Çoklu C2 yolu, GNSS'siz navigasyon, bütünlük izleme |
| Taktik hava riski azaltma | DAA (ADS-B, FLARM, akustik, görsel), Remote ID |
| Muhafaza (containment) | İki kademeli geofence, bağımsız FTS |

## 4. Uçuş testi programı

| Faz | İçerik | Çıkış ölçütü |
|---|---|---|
| UT-0 | Bağlı (tethered) hover, 8 motor | Kararlı hover, INDI kazanç ayarı |
| UT-1 | Serbest hover + bilinçli motor kesme (yerde 2 m, ağ altında) | Her motor için tolere edilen arıza |
| UT-2 | Kısa geçişler (90° → 45° → 90°) | Koridor takibi |
| UT-3 | Tam geçiş + seyir, batarya-only | Seyir performansı, L/D doğrulaması |
| UT-4 | Hidrojen sistemi entegre, 1 → 3 saat | Enerji modeli ile ±%5 uyum |
| UT-5 | GNSS kapalı uçuşlar (yazılımsal devre dışı), MagNav/TRN | Konum hatası < 50 m |
| UT-6 | RTA testleri: bilerek kötü AC komutları | Sıfır sert zarf ihlali |
| UT-7 | 3 araçlık sürü, görev dağıtımı + röle | Uzlaşı süresi, çatışma yok |
| UT-8 | Paraşüt açılım testleri (balast ile, sonra gerçek araç) | ≤ 5 m/s iniş |
