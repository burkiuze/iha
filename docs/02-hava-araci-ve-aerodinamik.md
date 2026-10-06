# 02 — Hava Aracı Yapısı ve Aerodinamik

## 1. Genel geometri

```
            Seyir görünümü (önden)                     Askı / yerde (yandan)

   ┌──────────────── 3,20 m ────────────────┐                 ▲ itki
   │  M1U    M2U    [gövde]   M3U    M4U    │  üst kanat         │
   ●──(○)────(◎)──────███──────(◎)────(○)───●                ┌──┴──┐
   ┃                  ███                   ┃  0,60 m       │ üst │ kanat
   ┃                  ███                   ┃  (açıklık)    │     │
   ●──(○)────(◎)──────███──────(◎)────(○)───●                │ alt │ kanat
   │  M1L    M2L               M3L    M4L   │  alt kanat     └┬───┬┘
   └─ uç levhası = iniş ayağı ──────────────┘                ▲   ▲ uç levhası ayakları
   (○) dış motor (sürekli)  (◎) iç motor (katlanır pervane)
```

| Parametre | Değer | Not |
|---|---|---|
| Kanat açıklığı (b) | 3,20 m | Her iki kanat |
| Kanatlar arası açıklık (h) | 0,60 m | h/b = 0,19 |
| Kademelenme (stagger) | 0,25 m | Üst kanat önde; stall'da yunuslama kararlılığı |
| Veter | 0,18 m (kök 0,21 / uç 0,15) | |
| Toplam kanat alanı (S) | 1,15 m² | 2 × 0,576 m² |
| Kanat başına açıklık oranı | ~17,8 | |
| Kanat yüklemesi | 212 N/m² (21,6 kg/m²) | |
| Profil | Laminer, ~%13 kalınlık, düşük Re (≈ 3,5·10⁵) için | |
| Geriye ok açısı | Üst +4°, alt −4° | Kutu çerçevede yönsel kararlılık |
| Uç levhası (tip fin) | 0,60 m yükseklik, NACA 0010 | Dikey kuyruk görevi + iniş ayağı |
| Gövde bölmesi | 0,95 m × 0,22 m × 0,18 m | Kanatlar arasında, AM'de |

### Neden kuyruk yok?
Kutu kanatta kademelenme (stagger) ve iki kanadın farklı geliş açısı
(decalage, +1,5°) birlikte "tandem" gibi davranır: ön (üst) kanat daha
yüklüdür ve önce stall'a girer → burun aşağı moment → doğal stall
kurtarması. Yönsel kararlılığı uç levhaları sağlar. Böylece kuyruk bomu,
yatay ve dikey kuyruk ortadan kalkar; kuyruk üstü duruş için gereken
"düz taban" (iniş ayakları) da uç levhalarıyla bedavaya gelir.

## 2. Aerodinamik performans

### 2.1 İndüklenmiş sürükleme kazancı
Prandtl'ın kutu kanat yaklaşımına göre aynı açıklık ve toplam taşımadaki
tek kanatla oran:

```
D_i,kutu / D_i,tek ≈ (1 + 0,45·h/b) / (1,04 + 2,81·h/b)
                   = (1 + 0,084) / (1,04 + 0,527) ≈ 0,69
```

Yani indüklenmiş sürüklemede **~%31 azalma**. Düşük hızlı, yüksek C_L
ile uzun süre loiter eden bir İHA'da indüklenmiş sürükleme toplamın
%40–50'sidir; bu, yaklaşık %13–15 toplam sürükleme kazancı demektir.

### 2.2 Seyir noktası

| Büyüklük | Değer | Hesap |
|---|---|---|
| Stall hızı (C_L,max = 1,45, flaperon ile) | 15,4 m/s | √(2·212 / (1,225·1,45)) |
| Seyir hızı | 28 m/s | |
| Seyir C_L | 0,44 | 2·212 / (1,225·28²) |
| L/D (seyir, 4 iç pervane katlı) | ≈ 18,5 | Kutu kanat + düşük ıslak alan |
| Sürükleme | ≈ 13,2 N | 244 N / 18,5 |
| Şaft gücü | ≈ 370 W | 13,2 · 28 |
| Elektrik gücü (itki) | ≈ 520 W | η_pervane 0,80 · η_motor+ESC 0,89 |
| Aviyonik + görev yükü | ≈ 70 W | |
| **Toplam seyir bara gücü** | **≈ 590 W** | Enerji modelinde kullanılır |
| En iyi dayanım hızı | ~22 m/s | C_L ≈ 0,72 |

### 2.3 Askı (hover)

| Büyüklük | Değer |
|---|---|
| Pervane | 8 × 16" (0,406 m), iç dördü katlanır |
| Toplam disk alanı | 1,04 m² |
| Disk yüklemesi | 235 N/m² |
| İdeal güç | T^1,5 / √(2ρA) ≈ 2,40 kW |
| Figure of merit | ~0,65 |
| **Askı bara gücü** | **≈ 3,7–3,8 kW** |
| Nominal itki/ağırlık | 1,61 (`hover_margin`) |
| Tek motor arızasıyla itki/ağırlık | 1,20 (dış) / 1,32 (iç) |

Askı süresi sorti başına ~90 s ile sınırlandırılır (kalkış + geçiş +
iniş). Bu kısa tepe yükü yakıt hücresi değil batarya + süperkap karşılar.

### 2.4 Geçiş (transition) koridoru
Tail-sitter'ın en kritik fazıdır. SİMURG'da:

1. **Dikey tırmanış** 40 m AGL'ye (rotor yıkaması + zemin etkisinden çıkış).
2. **Burun öne yatış**: 90° → 20° arası, tanımlı bir "hücum açısı – hız"
   koridorunda (tipik 5–7 s). Dağıtık itki kanat üzerinde akımı
   hızlandırdığı için (blown wing) kanat, serbest akım hızı stall hızının
   altındayken bile taşıma üretir.
3. **Seyre geçiş**: hava hızı ≥ 20 m/s olduğunda iç motorlar rölantiye
   iner, pervaneler aerodinamik olarak katlanır, mod CRUISE olur.

Geriye geçişte (seyir → askı) araç önce "burnunu kaldırarak" hızını keser
(kontrollü dikleşme; "pitch-up" manevrası). Rüzgâra karşı yapılır.

```
 Hücum açısı (°)
 90 ┤■■■■■ ASKI
    │      ■■
 60 ┤        ■■   ← izin verilen koridor (gri bölge)
    │          ■■■
 30 ┤             ■■■■
    │                 ■■■■■■
  5 ┤                       ■■■■■■■■■ SEYİR
    └──┬─────┬─────┬─────┬─────┬────► hava hızı (m/s)
       0     5     10    15    20   28
```

## 3. Yapı

| Eleman | Malzeme / yöntem |
|---|---|
| Kanat kirişleri | Pultrüzyon karbon boru (üst Ø16, alt Ø14 mm) |
| Kanat kabuğu | 0,3 mm karbon/aramid hibrit + Rohacell köpük çekirdek |
| Uç levhaları | Karbon sandviç; altta değiştirilebilir enerji sönümlü ayak (TPU kafes) |
| Gövde bölmesi | Karbon monokok; H₂ tankı bölmesinde patlama çıkışı (burst vent) panel |
| Motor nasel | Kanat hücum kenarına cıvatalı, 3D baskı CF-PA12; titreşim izolasyonu |
| Sökme-takma | Her kanat yarısı 2 hızlı bağlantı + kör geçmeli (blind-mate) konnektör; 2 kişi 10 dk'da toplar |

**Taşıma:** 4 kanat yarısı + gövde, 1,7 m × 0,5 m × 0,4 m'lik iki kutuya
sığar.

## 4. Kütle bütçesi

| Alt sistem | kg | MTOW % |
|---|---:|---:|
| Gövde, kutu kanat, uç levhaları | 6,20 | 24,9 |
| İtki (8 motor, 8 ESC, pervaneler, naseller) | 3,40 | 13,7 |
| PEM yakıt hücresi + yardımcı donanım (BoP) | 1,30 | 5,2 |
| H₂ tankı, 6,8 L / 300 bar, dolu | 3,20 | 12,9 |
| Li-ion batarya 12S2P (21700) | 1,70 | 6,8 |
| Süperkapasitör modülü | 0,30 | 1,2 |
| İnce film güneş paneli + MPPT | 0,60 | 2,4 |
| Aviyonik (3 FCC, IMU'lar, ağ anahtarları, kablo) | 1,60 | 6,4 |
| Navigasyon sensörleri (kameralar, LiDAR altimetre, manyetometre dizisi) | 0,80 | 3,2 |
| Haberleşme (C2, mesh, uydu, Remote ID) | 0,90 | 3,6 |
| Güvenlik (FTS + balistik paraşüt) | 0,90 | 3,6 |
| **Görev yükü** | **3,00** | **12,0** |
| Tasarım payı | 1,00 | 4,0 |
| **Toplam (MTOW)** | **24,90** | **100** |

Ağırlık merkezi (AM) her iki kanadın çeyrek veter noktaları arasındaki
doğrunun %42'sindedir; görev bölmesi AM üzerinde olduğundan yük değişimi
denge ayarını bozmaz. H₂ tankı da AM üzerindedir; yakıt tükendikçe AM
kaymaz (kütle ~0,14 kg azalır).
