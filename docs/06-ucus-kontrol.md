# 06 — Uçuş Kontrol

Referans modeller: [`simurg/config.py`](../simurg/config.py),
[`simurg/control/allocation.py`](../simurg/control/allocation.py)

## 1. Eksen takımları

Tail-sitter'da "burun" askıda yukarı, seyirde ileriye bakar. Kontrol
yasalarında tekillikten kaçınmak için **tek bir gövde ekseni takımı**
ve **kuaterniyon** kullanılır (Euler açıları yalnızca gösterim için).

Askı (hover) çerçevesi:
- **z**: yukarı = itki yönü (seyirde ileri)
- **x**: kanat düzlemine dik; üst kanat +x tarafında (seyirde "yukarı")
- **y**: kanat açıklığı, sağ +y

## 2. Kontrol mimarisi (kademeli)

```
 Konum/hız ─► [Dış döngü 50 Hz] ─► istenen ivme ─► [İtki yönü + yatış]
                                                        │
                                                        ▼
                    [Tutum döngüsü 250 Hz, kuaterniyon hatası, INDI]
                                                        │ istenen açısal ivme
                                                        ▼
                    [Kontrol dağıtıcı 250 Hz, sağlık farkındalıklı RPI]
                                                        │
                                       8 motor + 4 elevon komutu
```

### 2.1 Neden INDI?
**Artımlı doğrusal olmayan dinamik ters çevirme (INDI)**, modelin çoğunu
ölçülen açısal ivmeyle değiştirir; yalnızca eyleyici etkinliğini (B
matrisi) bilmeyi gerektirir. Bu, tail-sitter'da geçiş sırasında
aerodinamik katsayıların 90°'lik hücum açısı aralığında dramatik değişmesi
problemini büyük ölçüde ortadan kaldırır: aerodinamik momentler
"ölçülen bozucu" olarak otomatik telafi edilir.

```
Δu = B_eff⁺ · (ν_istenen − Ω̇_ölçülen) · J
u  = u_önceki + Δu
```

`B_eff`, sağlık vektörüyle ölçeklenmiş etkinlik matrisidir; bir motor
hasar gördüğünde INDI ve dağıtıcı **aynı anda** yeni gerçeğe uyum sağlar.

## 3. Askı etkinlik matrisi

`config.hover_effectiveness()` 4×12 B matrisini üretir. Satırlar
`[Fz, Mx, My, Mz]`, sütunlar 8 motor + 4 elevon:

| Eyleyici | Fz | Mx (roll) | My (pitch) | Mz (yaw) |
|---|---|---|---|---|
| Motor j | T_max | y_j·T_max | −x_j·T_max | k_Q·s_j·T_max |
| Elevon k | 0 | 0 | −h·F_max | −y_k·F_max |

Sayısal büyüklükler: T_max = 49 N, k_Q = 0,016 m, h = 0,35 m,
F_max = 6 N, motor y ∈ {±0,45, ±1,20}, elevon y = ±0,80.

**Yaw otoritesi:** Bir motorun yaw katkısı 0,016·49 ≈ 0,78 N·m iken bir
elevonun ≈ 0,80·6 = 4,8 N·m'dir. Elevonların pervane akımına yerleştirilmesi
bu yüzden tasarımın kilit noktasıdır.

## 4. Kontrol dağıtımı (RPI)

Algoritma (`ControlAllocator.allocate`):

1. Arızalı (h=0) eyleyiciler 0'da sabitlenir.
2. Serbest eyleyiciler için ağırlıklı sözde-ters çözüm:
   `u_f = (W_v·B_f)⁺ · W_v · (v − B_sabit·u_sabit)`
3. Sınır dışı çıkanlar sınırda sabitlenir; 2. adım tekrarlanır.
4. Hiç ihlal kalmayınca durulur (en fazla n+1 iterasyon → deterministik WCET).

**Eksen ağırlıkları** `W_v = diag(10, 100, 100, 1)` → istek fiziksel
olarak karşılanamazsa önce **yaw**, sonra **itki** feda edilir; roll ve
pitch (yani aracın devrilmemesi) en son. Bu davranış
`test_yaw_sacrificed_before_attitude_when_infeasible` ile doğrulanır.

### 4.1 Arıza senaryoları (referans modelden)

| Arıza | Hover marjı (T/W) | Sonuç |
|---|---|---|
| Yok | 1,61 | Nominal |
| Herhangi bir dış motor (ör. M1U) | 1,20 | Hover devam, görev sürdürülebilir |
| Herhangi bir iç motor (ör. M2U) | 1,32 | Hover devam |
| Aynı uçtaki iki motor (M1U + M1L) | 0,80 | **Hover yok** → seyirde kal, paraşüt/kayma iniş |
| Aynı kanadın iki ucu (M1U + M4U) | 0,92 | **Hover yok** |
| Köşegen iki motor (M1U + M4L) | 1,20 | Hover devam (simetri korunur) |

Hover marjı her FDIR güncellemesinde yeniden hesaplanır ve
`Context.hover_feasible` bayrağı ile acil durum yöneticisine aktarılır.
Böylece araç **dikey inişe başlamadan önce** inişin mümkün olup olmadığını
bilir.

## 5. Seyir kontrolü

Seyirde iç motorlar durur, pervaneler katlanır. Kontrol:

| Eksen | Birincil | İkincil |
|---|---|---|
| Roll | Diferansiyel elevon (sağ/sol) | Diferansiyel dış motor itkisi |
| Pitch | Kolektif elevon, üst ve alt kanat **ters** yönde | — |
| Yaw | Diferansiyel dış motor itkisi | Uç levhası (pasif) |
| Hız | Kolektif dış motor itkisi | |

Üst ve alt kanattaki elevonlar ters yönde sapınca saf pitch momenti
(taşıma değişimi minimal) üretir; aynı yönde sapınca **doğrudan taşıma
kontrolü** (direct lift control) sağlar — rüzgâr hamlesinde irtifayı
gövde açısını değiştirmeden korumak için kullanılır. Bu, klasik sabit
kanatlılarda olmayan bir serbestlik derecesidir.

## 6. Geçiş kontrolü

Geçiş, hava hızına göre planlanmış bir **referans yörünge** izler (bkz.
[02](02-hava-araci-ve-aerodinamik.md) koridor grafiği). INDI iç döngüsü
sayesinde ayrı bir "geçiş kontrolcüsü" yoktur; tek fark, B matrisinin
hava hızı ve hücum açısının fonksiyonu olarak harmanlanmasıdır:

```
B(V, α) = (1 − σ)·B_askı + σ·B_seyir(V),   σ = sat((V − 5) / 15, 0, 1)
```

Geçiş, koridordan ±10° sapma veya hava hızında beklenmedik düşüş olursa
**iptal edilir** (TRANSITION_FW → TRANSITION_VTOL), araç askıya döner.

## 7. Rüzgâr ve hamle yönetimi

- **Askıda:** Büyük kanat alanı yan rüzgâra duyarlıdır. Araç rüzgâr
  kestirimine göre **kanat düzlemini rüzgâra paralel** olacak şekilde yaw
  yapar (weathervaning); yan kuvvet minimuma iner.
- **Seyirde:** Doğrudan taşıma kontrolü + süperkapasitörden gelen ani güç
  ile hamle sırasında irtifa ve hız korunur.
- **İnişte:** Son 5 m'de radar/LiDAR altimetre ile zemin etkisi kompanze
  edilir; uç levhası ayaklarında yük hücresi ile temas algılanır,
  itki 300 ms'de kesilir (zıplama yok).
