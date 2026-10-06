# 01 — Sistem Gereksinimleri

Her gereksinim benzersiz bir kimlik taşır ve doğrulama yöntemi ile
(A: Analiz, T: Test, D: Gösterim, I: İnceleme) ilişkilendirilir. "Kod"
sütunu, referans modelde gereksinimi doğrulayan testi gösterir.

## 1. Görev ve performans

| Kimlik | Gereksinim | Doğr. | Kod |
|---|---|---|---|
| SYS-PER-001 | Azami kalkış ağırlığı (MTOW) ≤ 24,9 kg. | A, I | `config.MTOW_KG` |
| SYS-PER-002 | Pist, katapult veya ağ gerektirmeden 3 m × 3 m alandan dikey kalkış/iniş. | D | — |
| SYS-PER-003 | Seyir hızı 28 m/s, azami 38 m/s, stall ≤ 15,5 m/s. | A, T | `rta.Envelope` |
| SYS-PER-004 | Yalnız hidrojenle (güneşsiz) dayanım ≥ 3,2 sa, 3 kg görev yükü ile. | A, T | `test_energy.test_endurance_hydrogen_phase_without_solar` |
| SYS-PER-005 | 25 km yarıçapta görev; 50 km'ye kadar röle üzerinden. | A | — |
| SYS-PER-006 | Rüzgâr: askıda 10 m/s ortalama + 5 m/s hamle; seyirde 15 m/s. | A, T | — |
| SYS-PER-007 | Çalışma sıcaklığı −20 °C … +45 °C; yağmur IP54. | T | — |
| SYS-PER-008 | Görev bölmesi: 3,0 kg, 120 W sürekli, 1 GbE + 2× CAN-FD. | I, T | — |

## 2. Güvenlik ve arıza toleransı

| Kimlik | Gereksinim | Doğr. | Kod |
|---|---|---|---|
| SYS-SAF-001 | Askıda herhangi bir tek motor arızasında araç kontrollü hover yapabilmeli (itki/ağırlık ≥ 1,15). | A, T | `test_allocation.test_any_single_motor_failure_still_hovers` |
| SYS-SAF-002 | Askıda hover edilemeyen çoklu arıza 100 ms içinde tespit edilip acil prosedür başlatılmalı. | A, T | `test_allocation.test_same_tip_double_failure_detected_as_not_hoverable`, `test_modes` |
| SYS-SAF-003 | Fiziksel olarak karşılanamayan kontrol isteğinde yaw, roll/pitch'ten önce feda edilmeli. | T | `test_allocation.test_yaw_sacrificed_before_attitude_when_infeasible` |
| SYS-SAF-004 | Tamamen duran motor tek çevrimde (≤ 4 ms) FAILED ilan edilmeli. | T | `test_fdir.test_dead_motor_immediate` |
| SYS-SAF-005 | Sabit kısmi pervane hasarı DEGRADED olarak sınıflanmalı; sağlık değeri gerçek itki oranına yakınsamalı; zamanla FAILED'a tırmanmamalı. | T | `test_fdir.test_degraded_prop_detected_with_partial_health` |
| SYS-SAF-006 | Üç şeritli oylamada sürekli sapan şerit ≤ 5 çevrimde yalıtılmalı. | T | `test_fdir.test_voter_isolates_drifting_lane` |
| SYS-SAF-007 | Gelişmiş (YZ) kontrolcünün komutu 3 s ufukta yumuşak zarfı ihlal edecekse güvenlik kontrolcüsü devreye girmeli. | T | `test_rta.*` |
| SYS-SAF-008 | Sert zarf ihlali RTA'yı uçuş sonuna dek kilitlemeli. | T | `test_rta.test_hard_violation_latches` |
| SYS-SAF-009 | Uçuş sonlandırma sistemi (FTS) ana aviyonikten bağımsız güç, işlemci ve alıcıya sahip olmalı. | I | — |
| SYS-SAF-010 | Balistik paraşüt 40 m AGL üzerinde tam açılım sağlamalı; iniş hızı ≤ 5 m/s. | T | — |
| SYS-SAF-011 | Geofence: yumuşak sınır 50 m, sert sınır 10 m; sert sınır aşımında FTS. | T | `test_rta.test_fence_prediction` |

## 3. Enerji

| Kimlik | Gereksinim | Doğr. | Kod |
|---|---|---|---|
| SYS-PWR-001 | DC bara güç dengesi her çevrimde sağlanmalı; karşılanamayan yük sıfır. | T | `test_energy.test_bus_balance_and_no_brownout` |
| SYS-PWR-002 | Yakıt hücresi güç değişim hızı ≤ 60 W/s. | T | `test_energy.test_fuel_cell_slew_limited` |
| SYS-PWR-003 | Ani yük basamaklarının ilk anı süperkapasitörce karşılanmalı. | T | `test_energy.test_supercap_absorbs_step` |
| SYS-PWR-004 | Eve dönüş fizibilitesi her 1 s'de, %30 pay ve iniş enerjisi dahil hesaplanmalı; batarya %20 rezervi bu hesaba katılmamalı. | T | `test_energy.test_return_home_decision` |
| SYS-PWR-005 | Hidrojen bitse dahi batarya ile ≥ 20 dk seyir + VTOL iniş. | A | — |

## 4. Navigasyon

| Kimlik | Gereksinim | Doğr. | Kod |
|---|---|---|---|
| SYS-NAV-001 | ≥ 4 bağımsız konum kaynağı (GNSS, VIO, TRN, MagNav). | I | — |
| SYS-NAV-002 | Tek hatalı kaynak (ör. 200 m GNSS sahteciliği) tespit edilip dışlanmalı; çözüm hatası < 30 m. | T | `test_nav.test_gnss_spoof_excluded` |
| SYS-NAV-003 | Yanlış alarm olasılığı ≤ 1e−5 / test; kaçırılmış tespit ≤ 1e−7. | A | `nav.IntegrityMonitor` |
| SYS-NAV-004 | Koruma seviyesi > alarm limiti (50 m) ise bütünlük kaybı bildirilip LOITER_HOLD'a geçilmeli. | T | `test_nav`, `test_modes` |

## 5. Otonomi, mod ve acil durum

| Kimlik | Gereksinim | Doğr. | Kod |
|---|---|---|---|
| SYS-AUT-001 | Uçuş modları açık geçiş tablosu ile tanımlanmalı; tablo dışı geçiş reddedilmeli. | T | `test_modes` |
| SYS-AUT-002 | Ön uçuş kontrolü geçmeden silahlanma (ARM) yapılamaz. | T | `test_modes.test_cannot_arm_without_preflight` |
| SYS-AUT-003 | Geçiş hızına ulaşılmadan seyir moduna geçilemez. | T | `test_modes.test_cannot_transition_to_cruise_below_speed` |
| SYS-AUT-004 | Acil durum önceliği: kontrol kaybı > enerji/hover > eve dönüş enerjisi > nav bütünlüğü > bağlantı kaybı. | T | `test_modes.test_contingency_priorities` |
| SYS-AUT-005 | C2 bağlantı kaybı 30 s sürerse otomatik eve dönüş. | T | `test_modes` |

## 6. Sürü

| Kimlik | Gereksinim | Doğr. | Kod |
|---|---|---|---|
| SYS-SWM-001 | Her görev en fazla bir ajana atanmalı. | T | `test_swarm.test_each_task_at_most_once_and_energy_feasible` |
| SYS-SWM-002 | Hiçbir ajan rotası, %25 rezerv hariç enerji bütçesini aşmamalı. | T | aynı |
| SYS-SWM-003 | Dağıtım deterministik olmalı (aynı girdi → aynı çıktı; dağıtık uzlaşı için şart). | T | `test_swarm.test_deterministic` |
| SYS-SWM-004 | Ulaşılamayan görev atanmadan bırakılmalı ve operatöre bildirilmeli. | T | `test_swarm.test_unreachable_task_left_unassigned` |

## 7. Siber güvenlik ve düzenleyici

| Kimlik | Gereksinim | Doğr. | Kod |
|---|---|---|---|
| SYS-SEC-001 | Güvenli önyükleme: tüm yazılım imajları donanım güven kökü ile doğrulanmalı. | T | — |
| SYS-SEC-002 | Görev planları operatör anahtarıyla imzalı olmalı; imzasız plan yüklenemez. | T | — |
| SYS-SEC-003 | Tüm C2 trafiği kimlik doğrulamalı şifreleme (AEAD) ile korunmalı; tekrar saldırısına karşı sayaç. | T | — |
| SYS-REG-001 | ASTM F3411 uyumlu yayın tipi Remote ID. | T | — |
| SYS-REG-002 | EASA SORA / SHGM İHA talimatı kapsamında "spesifik" kategori operasyon dosyası. | I | — |
