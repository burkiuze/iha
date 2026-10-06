# 09 — Sürü ve İş Birliği

Referans model: [`simurg/swarm/auction.py`](../simurg/swarm/auction.py)

## 1. Neden sürü?

Tek bir SİMURG ~3,5 saatte ~350 km yol kat eder. Deprem sonrası 400 km²'lik
bir alanın 100 m şerit aralığıyla taranması ~4000 km'dir: tek araçla
günler, 8 araçlık bir sürüyle **bir öğleden sonra**. Ayrıca sürü:
- aralarındaki araçları **haberleşme rölesi** olarak kullanarak menzili
  dağlık arazide uzatır;
- bir aracın arızasını diğerlerinin görevleri yeniden paylaşmasıyla tolere
  eder;
- aynı hedefi farklı açılardan görerek algılama güvenini artırır.

## 2. Görev dağıtımı: zaman indirgemeli CBBA

**Problem:** N araç, M görev (arama hücresi, hedef doğrulama, röle
noktası…). Her görevin önceliği ve süresi var; her aracın farklı enerjisi.

**Ödül:** Bir göreve ne kadar geç ulaşılırsa değeri o kadar düşer
(arama-kurtarmada her dakika hayati):

```
ödül_rota = Σ öncelik_k · exp(−varış_k / τ),   τ = 3600 s
```

**Teklif:** Her araç her atanmamış görevi rotasının her konumuna eklemeyi
dener; marjinal skor = yeni rota ödülü − eski rota ödülü. Ekleme sonraki
görevleri geciktirdiği için bu fark, aracın mevcut yükünü otomatik
cezalandırır → yük **doğal olarak dengelenir**.

**Fizibilite:** Rota + görev süreleri + üsse dönüş enerjisi
`enerji · (1 − %25 rezerv)` bütçesini aşamaz.

**Kazanan:** Global en yüksek teklif. Eşitlikte araç kimliği sırası
(determinizm).

### 2.1 Dağıtık uzlaşı
Uçuşta merkezi bir hakem yoktur. Her araç:
1. Kendi rotasını (bundle) yerel olarak kurar.
2. Komşularına `(görev, kazanan, teklif, zaman damgası)` tablosunu yayar.
3. CBBA uzlaşı kurallarıyla (daha yüksek teklif kazanır; eşitlikte küçük
   kimlik; daha yeni zaman damgası bilgi önceliği) çatışmaları çözer;
   kaybettiği görevi ve **ondan sonraki** tüm görevleri rotasından çıkarır.
4. Ağın çapı D ise en fazla `N·M·D` turda tüm araçlar aynı, çatışmasız
   atamaya ulaşır.

Referans model bu sürecin **sonucunu** deterministik olarak üretir; dağıtık
uygulama her zaman bu sonuçla karşılaştırılarak test edilir
(`test_deterministic`).

### 2.2 Dinamik olaylar

| Olay | Tepki |
|---|---|
| Yeni görev (ör. termal kamera bir termal anomali buldu → "doğrula" görevi) | Yalnızca o görev için yeni teklif turu |
| Araç enerjisi beklenenden hızlı düştü | Rotasının sonundan görev bırakır, diğerleri teklif verir |
| Araç kayboldu (heartbeat > 10 s) | Tüm görevleri "atanmamış"a döner |
| Ulaşılamayan görev | Atanmaz, operatöre raporlanır (`test_unreachable_task_left_unassigned`) |

## 3. Ağ: kendini onaran mesh

- **Radyo:** Lisanssız alt-GHz (uzun menzil, düşük hız; kontrol ve
  uzlaşı) + 2,4/5 GHz (yüksek hız; video).
- **Yönlendirme:** Konum farkındalıklı, bağlantı kalitesi metrikli
  (ETX) proaktif yönlendirme; topoloji her 1 s güncellenir.
- **Röle görevi:** Planlayıcı, yer istasyonu ile uzak araçlar arasında
  bağlantı kopacağını öngördüğünde (arazi gölgesi analizi, sayısal
  yükseklik modeli ile) bir aracı **röle noktası** görevine atar; bu
  görev, normal görevlerle aynı açık artırmaya girer ama yüksek öncelikle.
- **Bant genişliği önceliği:** C2/uzlaşı > telemetri > algılama olayları
  (küçük, meta veri) > küçük resim (thumbnail) > tam video.

## 4. Çarpışmadan kaçınma (sürü içi)

- Her araç 5 Hz'de konum/hız yayar.
- **İrtifa katmanları:** Her araca seyirde ayrı 15 m'lik irtifa katmanı;
  katman değiştirme yalnızca sürü içi CPA > 100 m ise.
- **Hız engel (velocity obstacle) temelli** yerel kaçınma; RTA zarfı
  içinde kalır.
- VTOL bölgesinde (üs çevresi 150 m) **zaman dilimli iniş/kalkış sırası**;
  aynı anda tek araç askıda.

## 5. Ortak algılama

Bir araç bir "aday" (ör. enkaz altında ısı izi) tespit ettiğinde:
1. Olay (konum, sınıf, güven, küçük resim) sürüye yayılır.
2. "Doğrulama" görevi farklı bir açıdan bakabilecek araca atanır.
3. İki bağımsız gözlemin Bayes füzyonu ile güven eşiği aşılırsa
   operatöre **yüksek öncelikli** bildirim gider; müdahale kararı ve
   saha ekiplerinin yönlendirilmesi insan operatördedir.

> **Durum:** Sürü görev dağıtımı (`simurg/swarm/auction.py`) bağımsız bir
> referans modeldir; 6-DOF simülasyon çekirdeğine henüz bağlı değildir
> (**planlanan**).
