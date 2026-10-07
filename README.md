# SİMURG — Kutu Kanatlı, Hidrojen-Hibrit, Kuyruk Üstü Kalkışlı İHA Mimarisi

> **SİMURG**; Prandtl kutu kanadını, kuyruk üstü (tail-sitter) dikey
> kalkışı, 8 motorlu dağıtık elektrik itkiyi, hidrojen yakıt hücresi +
> batarya + süperkapasitör + güneş enerjisini, farklı mimarili üçlü uçuş
> bilgisayarını, GNSS'e muhtaç olmayan navigasyonu ve yapay zekâyı
> güvenli bir "kafes" içinde kullanan çalışma zamanı güvencesini tek bir
> 25 kg sınıfı **sivil** İHA kavramında birleştiren bir referans mimari ve
> **araştırma / dijital ikiz simülasyon platformudur**.

**Kapsam:** sivil araştırma, arama-kurtarma, afet gözlemi, çevre izleme,
altyapı denetimi, uçuş güvenliği araştırması, yazılım doğrulaması ve
arıza toleransı. Bu depo **uçuşa hazır yazılım değildir**: gerçek araç
için kontrol kazancı, motor/ESC kalibrasyonu, hidrojen sistemi kurulumu ya
da uçuş prosedürü içermez. Silahlandırma, hedef takibi, yük bırakma veya
zarar verici kullanım amacı yoktur.

## Uygulama durumu

| Bileşen | Durum | Kod |
|---|---|---|
| 6-DOF simülasyon çekirdeği (sabit 14 adımlı tick, deterministik) | **var** | `simurg/sim/engine.py` |
| Aerodinamik arayüz: analitik (±180°) ve tablo tabanlı | **var** (sentetik katsayılar) | `simurg/aero/` |
| Rejime bağlı kontrol etkinliği B(V, σ) + arıza toleranslı dağıtım | **var** | `simurg/control/effectiveness.py`, `allocation.py` |
| Tail-sitter geçiş koordinatörü (iptal mantığı dahil) | **var** | `simurg/control/transition.py` |
| Eyleyici, sensör, ortam modelleri | **var** | `simurg/sim/actuators.py`, `sensors.py`, `environment.py` |
| Zaman tabanlı arıza enjeksiyonu | **var** | `simurg/sim/faults.py` |
| Simplex RTA (açıklanabilir kararlar, mühürlü `ValidatedCommand`) | **var** | `simurg/safety/rta.py` |
| Komut doğrulayıcı (öneri → RTA öncesi tip/sonluluk/fiziksel sınır reddi) | **var** | `simurg/safety/command_validator.py` |
| YZ yetki sınırı ve güvenlik değişmezleri (kodla zorlanır, test edilir) | **var** | `docs/08` §6, `tests/test_safety_invariants.py` |
| Fail-safe: bilinmeyen ≠ sağlıklı | **var** | `docs/08` §6.1, `tests/test_failsafe.py` |
| FDIR (standart sağlık raporları) | **var** | `simurg/fdir/monitor.py` |
| Araç sağlık modeli (6 alan → NOMINAL/DEGRADED/FAILED/UNKNOWN) | **var** (bilgisayar şeritleri modellenmez) | `simurg/fdir/vehicle_health.py` |
| Uçuş öncesi denetçi (8 kontrol; hepsi geçmeden ARMED yok) | **var** | `simurg/sim/preflight.py` |
| Sistem denetçisi (NORMAL/DEGRADED/CONTINGENCY/EMERGENCY; eyleyici sürmez) | **var** | `simurg/sim/supervisor.py` |
| Çok kaynaklı navigasyon bütünlüğü → `NavigationSolution` | **var** | `simurg/nav/` |
| Hibrit enerji yönetimi → `EnergyState` | **var** | `simurg/power/energy_manager.py` |
| Mod makinesi + tek kaynak acil durum kural tablosu | **var** | `simurg/modes/flight_modes.py` |
| Olay yolu, JSON kayıt, tekrar oynatma, metrikler | **var** | `simurg/core/events.py`, `simurg/sim/` |
| Monte Carlo altyapısı (tohumla yeniden üretim) | **var** (sıralı) | `simurg/sim/montecarlo.py` |
| Sürü görev dağıtımı (CBBA referansı) | **prototip** (simülasyona bağlı değil) | `simurg/swarm/auction.py` |
| INDI iç döngü, tutum kestiricisi, blown-wing aero | **planlanan** | — |
| Farklı mimarili FCC şeritleri, TSN ağı, kriptografi, GCS | **planlanan** (yalnızca mimari doküman) | `docs/04`, `docs/10`, `docs/11`, `docs/15` |
| Ayrıntılı sistem mimarisi kaydı (236 blok, üretilmiş diyagram + matris, yetki yolu testi) | **var** | `simurg/architecture/`, `docs/15` |

## Ayrıntılı sistem mimarisi

[docs/15-sistem-mimarisi.md](docs/15-sistem-mimarisi.md) SİMURG'u
"system-of-systems" düzeyinde **23 alt sistem, 236 blok ve 304 bağlantı**
olarak tanımlar: sensör zinciri (sürücü → koşullandırma → zaman damgası →
akla yatkınlık → sağlık → füzyon), görev bilgisayarı, navigasyon hattı,
GNC, RTA iç yapısı, üç FCC şeridi (karşılaştırıcı, oylayıcı, monitör),
kontrol dağıtım zinciri, eyleyici soyutlaması, FDIR omurgası + araç sağlık
modeli, enerji, mod/acil durum, haberleşme, veri yolu, zaman, yapılandırma,
uçuş kayıt cihazı, dijital ikiz, yer istasyonu, uçuş öncesi ve sistem
denetçileri.

Her blok kodla karşılaştırılarak işaretlenmiştir: **118 IMPLEMENTED,
55 PARTIAL, 63 PLANNED**. Diyagramlar ve bileşen matrisi
`simurg/architecture/registry.py` kaydından üretilir
(`python -m simurg.architecture --update docs/15-sistem-mimarisi.md`);
`tests/test_architecture.py` kod referanslarının var olduğunu, PLANNED
blokların kod iddia etmediğini, belgenin kayıtla senkron olduğunu ve öneri
katmanından eyleyicilere yetki geçidini atlayan bir yol olmadığını denetler.

```mermaid
flowchart LR
  SEN[Sensörler] --> NAV[Navigasyon + bütünlük] --> GNC[GNC]
  MC["Görev bilgisayarı / YZ<br/>(yalnızca öneri)"] == öneri ==> VAL[Komut doğrulayıcı] ==> RTA{{Simplex RTA}}
  GNC == öneri ==> VAL
  RTA == ValidatedCommand ==> CTRL[Kontrol] ==> FCC[FCC şeritleri A/B + monitör C] ==> AL[Dağıtım] ==> ACT[8 motor + 4 elevon]
  FDIR[FDIR → araç sağlık modeli] -.-> CONT[Mod & acil durum]
  EN[Enerji] -.-> CONT
  CONT -.-> CTRL
  PRE[Uçuş öncesi denetçi] -.-> CONT
  FDIR -.-> SUP[Sistem denetçisi]
  CONT -.-> SUP
```

## Simulation & Digital Twin

```mermaid
flowchart LR
  S[Senaryo] --> E[Ortam] --> SN[Sensörler] --> N[Navigasyon] --> P[Kontrolcü önerisi]
  P --> R{RTA} --> A[Kontrol dağıtımı] --> AC[Eyleyiciler] --> D[6-DOF dinamik]
  D --> ST[Durum] --> L[Kayıt / Metrikler]
  F[Arıza takvimi] -.-> E & SN & AC & N
```

```python
from simurg.sim import SimulationEngine, get_scenario, ReplaySession

result = SimulationEngine(get_scenario("transition_abort", seed=3)).run()
print(result.passed, result.metrics.final_mode, result.metrics.transitions_aborted)
ReplaySession.from_source(result).rta_history()
```

Komut satırı:

```bash
python -m simurg.sim list                                   # hazır senaryolar
python -m simurg.sim run nominal --seed 1 --json kayit.json # tek koşu + JSON kayıt
python -m simurg.sim replay kayit.json                      # zaman çizelgesi
python -m simurg.sim montecarlo combined_degraded --runs 20 --seed 0 --wind 6
python -m simurg.sim montecarlo combined_degraded --wind 6 --reproduce <TOHUM>
```

Hazır senaryolar: `nominal`, `nav_source_loss`, `nav_integrity_loss`,
`single_actuator_degradation`, `communication_loss`,
`energy_reserve_warning`, `rta_intervention`, `transition_abort`,
`combined_degraded`, `hover_capability_loss`, `loss_of_control`. Her biri beklenen güvenlik sonuçlarını tanımlar ve
testlerde doğrulanır.

### YZ yetki sınırı

```
YZ / gelişmiş kontrolcü --Command (öneri)--> CommandValidator --> RuntimeAssurance
    --ValidatedCommand--> VehicleController (kontrol soyutlaması) --> kontrol dağıtımı --> eyleyiciler
```

Kontrol katmanı ham öneri kabul etmez; `ValidatedCommand` yalnızca RTA
tarafından üretilebilir. `CommandValidator` tip hatalı, sonlu olmayan ya
da fiziksel sınır dışı öneriyi **kırpmadan reddeder**; bu durumda RTA
güvenlik kontrolcüsünü seçer (`gecersiz_oneri`). YZ katmanının eyleyicilere içe aktarma yolu
yoktur. Bunlar testlerle zorlanan değişmezlerdir (docs/08 §6).

### Kanonik API

| Kavram | Kanonik yer | Geriye dönük uyumluluk |
|---|---|---|
| Merkezi durum | `simurg.core.types.VehicleState` | — |
| RTA durum görünümü | `simurg.safety.rta.EnvelopeState` | `simurg.safety.rta.VehicleState` (takma ad) |
| RTA kararı | `RuntimeAssurance.decide()` -> `SafetyDecision` | `RuntimeAssurance.select()` |
| Mod geçişi | `FlightModeMachine.request_detailed()` | `FlightModeMachine.request()` |
| Acil durum kararı | `ContingencyManager.evaluate_detailed()` | `ContingencyManager.evaluate()` |
| Kontrol etkinliği | `simurg.control.effectiveness` | `simurg.config.hover_effectiveness()` |

Ayrıntılar (tick sırası, durum modeli, kayıt şeması, determinizm,
sınırlamalar, simülasyon bulguları):
[docs/14-simulasyon-ve-dijital-ikiz.md](docs/14-simulasyon-ve-dijital-ikiz.md).

## Klasik İHA'lardan 10 temel fark (mimari)

| # | Klasik yaklaşım | SİMURG |
|---|---|---|
| 1 | Quadplane: seyirde ölü ağırlık olan ayrı dikey motorlar | **Tail-sitter:** aynı 8 motor hem askı hem seyir |
| 2 | Tek kanat + kuyruk | **Kutu kanat:** daha az indüklenmiş sürükleme (el hesabı ~%31), kuyruksuz, uç levhaları = iniş takımı |
| 3 | Seyirde tüm pervaneler sürükleme yapar | **İç 4 pervane katlanır**, dış 4'ü çalışır |
| 4 | Tek enerji kaynağı | **H₂ PEM + Li-ion + süperkap + güneş**, frekans ayrıştırmalı yönetim |
| 5 | Askıda motor arızası = düşüş | **Herhangi tek motor arızası askıda tolere** (testle doğrulanır) |
| 6 | Aynı 3 bilgisayar (ortak mod hatası) | **Farklı mimarili üçlü:** ARM + C, RISC-V + Rust, FPGA monitör (planlanan) |
| 7 | GNSS = gerçek | **Çok kaynaklı navigasyon**, hata dışlama, koruma seviyesi |
| 8 | YZ ya hiç yok ya doğrudan kontrolde | **Simplex RTA:** gelişmiş kontrolcü önerir, güvenlik çekirdeği denetler |
| 9 | Sabit görev yükü | **Sıcak değiştirilebilir, imzalı kendini tanıtan** görev bölmesi (planlanan) |
| 10 | Tek araç | **CBBA** ile sürü görev paylaşımı (prototip) |

## Sayısal değerler: nereden geliyor?

| Parametre | Değer | Kaynak |
|---|---|---|
| MTOW | 24,9 kg | Tasarım bütçesi (`docs/02`) |
| Askıda T/W (nominal / tek motor arızası) | 1,61 / ≥ 1,20 | **Testle doğrulanır** (`test_allocation`) |
| Seyir L/D, stall hızı | ≈ 18,5 / 15,4 m/s | Tasarım hedefi; sentetik aero modelinde stall ≈ 18 m/s (**açık**, `docs/01` SYS-PER-003) |
| Askı bara gücü | El hesabı ≈ 3,8 kW; 6-DOF simülasyonu ≈ 4,3 kW | Simülasyon ölçümü (`docs/14` §11) |
| Geçiş tepe bara gücü | ≈ 9 kW | Simülasyon ölçümü (sentetik model) |
| Dayanım (yalnız H₂, güneşsiz) | > 3,2 sa hedefi | Yalnızca enerji modeliyle (`test_energy`); uçuşla doğrulanmadı |

Fiziksel katsayıların tümü sentetiktir; CFD, rüzgâr tüneli, tezgâh ya da
uçuş testiyle doğrulanmamıştır.

## Depo yapısı

```
docs/                       Mimari dokümanları (00–15)
simurg/
  config.py                 v0.1 sabitleri ve askı geometrisi (geriye dönük uyumlu)
  core/                     Ortak tipler, olay yolu, hatalar, yapılandırma, eksen takımları
  aero/                     Aerodinamik model arayüzü, analitik + tablo modelleri
  control/                  Kontrol dağıtımı, etkinlik B(V,σ), geçiş, iç döngü, güdüm
  power/                    Hibrit enerji yönetimi
  safety/                   Simplex RTA, komut doğrulayıcı
  fdir/                     Motor/yüzey sağlık izleme, şerit oylama, araç sağlık modeli
  modes/                    Uçuş modu durum makinesi, acil durum kuralları
  nav/                      Bütünlük izleme, navigasyon sağlayıcıları
  swarm/                    Sürü görev dağıtımı (prototip)
  sim/                      6-DOF motor, senaryolar, arıza, kayıt, replay, Monte Carlo, CLI,
                            uçuş öncesi denetçi, sistem denetçisi
  architecture/             Mimari bileşen kaydı + Mermaid/matris üretici (docs/15)
tests/                      Gereksinimlere izlenen testler (+ izlenebilirlik denetimi)
examples/                   simulation_demo, fault_injection_demo, replay_demo, senaryo_demo (v0.1)
```

## Çalıştırma

Gereksinim: Python ≥ 3.10, NumPy. Başka çalışma zamanı bağımlılığı yoktur
(SciPy, Pandas, ROS vb. bilinçli olarak kullanılmaz). Tamamen çevrimdışı
çalışır; dış servis, ağ erişimi ya da gizli bilgi gerektirmez.

```bash
pip install -e .                              # ya da yalnızca: pip install numpy
python3 -m unittest discover -s tests -v     # ~210 test, ~4–5 dk (senaryo koşuları dahil)
simurg-sim list                               # = python -m simurg.sim list
python3 examples/simulation_demo.py nominal
python3 examples/fault_injection_demo.py
python3 examples/replay_demo.py
```

CI (`.github/workflows/tests.yml`): Python 3.10 / 3.11 / 3.12 üzerinde
kurulum, tüm testler ve örnek/CLI duman testi. Dağıtım, donanım ya da
gizli bilgi içermez.

Kütüphane varsayılan olarak terminale yazmaz (`logging` + `NullHandler`);
ayrıntılı çıktı için `python -m simurg.sim -v run ...`.

## Gereksinim izlenebilirliği

[docs/01-gereksinimler.md](docs/01-gereksinimler.md) her gereksinimi
test(ler)e, `SYS-SIM-*` gereksinimlerini ayrıca uygulama dosyasına bağlar.
`tests/test_traceability.py` bu bağlantıların gerçekten var olduğunu
otomatik denetler.

## Dokümanlar

| # | Bölüm |
|---|---|
| 00 | [Konsept ve klasik İHA'lardan farklar](docs/00-konsept-ve-farklar.md) |
| 01 | [Sistem gereksinimleri (izlenebilir)](docs/01-gereksinimler.md) |
| 02 | [Hava aracı yapısı ve aerodinamik](docs/02-hava-araci-ve-aerodinamik.md) |
| 03 | [Güç ve itki sistemi](docs/03-guc-ve-itki.md) |
| 04 | [Aviyonik donanım](docs/04-aviyonik-donanim.md) |
| 05 | [Yazılım mimarisi](docs/05-yazilim-mimarisi.md) |
| 06 | [Uçuş kontrol](docs/06-ucus-kontrol.md) |
| 07 | [GNSS'ten bağımsız navigasyon](docs/07-navigasyon.md) |
| 08 | [Otonomi, RTA ve FDIR](docs/08-otonomi-ve-guvenlik.md) |
| 09 | [Sürü ve iş birliği](docs/09-suru-ve-isbirligi.md) |
| 10 | [Haberleşme ve siber güvenlik](docs/10-haberlesme-ve-siber-guvenlik.md) |
| 11 | [Yer segmenti ve dijital ikiz](docs/11-yer-segmenti-ve-dijital-ikiz.md) |
| 12 | [Doğrulama ve sertifikasyon](docs/12-dogrulama-ve-sertifikasyon.md) |
| 13 | [Riskler ve yol haritası](docs/13-riskler-ve-yol-haritasi.md) |
| 14 | [Simülasyon ve dijital ikiz çekirdeği](docs/14-simulasyon-ve-dijital-ikiz.md) |
| 15 | [Ayrıntılı sistem mimarisi (Detailed System Architecture)](docs/15-sistem-mimarisi.md) |

## Lisans

Apache-2.0 — bkz. [LICENSE](LICENSE).
