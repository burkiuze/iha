# 01 — Sistem Gereksinimleri

Her gereksinim benzersiz bir kimlik taşır ve doğrulama yöntemi ile
(A: Analiz, T: Test, D: Gösterim, I: İnceleme) ilişkilendirilir. "Kod"
sütunu, referans modelde gereksinimi doğrulayan testi gösterir.
§8'deki simülasyon gereksinimlerinde ayrıca "Uygulama" sütunu vardır
(Gereksinim → Uygulama → Test üçlüsü).

İzlenebilirlik otomatik denetlenir: `tests/test_traceability.py`, bu
dosyadaki her `test_<modül>.<test_adı>` referansının gerçekten var
olduğunu ve her `SYS-SIM` gereksiniminin bir uygulama dosyasına ve en az
bir teste bağlandığını doğrular.

**Durum notu:** §1'deki performans değerleri kavramsal tasarım hedefleridir.
6-DOF simülasyonu sentetik aero katsayılarıyla çalışır ve bazı hedefleri
henüz doğrulamaz (ör. SYS-PER-003: sentetik modelde C_L,max ≈ 1,0 ->
stall ≈ 18 m/s; flaperon modellenmedi). Bu tür satırlar "açık" olarak işaretlidir.

## 1. Görev ve performans

| Kimlik | Gereksinim | Doğr. | Kod |
|---|---|---|---|
| SYS-PER-001 | Azami kalkış ağırlığı (MTOW) ≤ 24,9 kg. | A, I | `config.MTOW_KG` |
| SYS-PER-002 | Pist, katapult veya ağ gerektirmeden 3 m × 3 m alandan dikey kalkış/iniş. | D | — |
| SYS-PER-003 | Seyir hızı 28 m/s, azami 38 m/s, stall ≤ 15,5 m/s. **Açık:** sentetik aero modelinde stall ≈ 18 m/s; simülasyon seyri 24 m/s ile yapılır. | A, T | `rta.Envelope` |
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
| SYS-AUT-004 | Acil durum önceliği: kontrol kaybı > enerji/hover > eve dönüş enerjisi > nav bütünlüğü > bağlantı kaybı. | T | `test_modes.test_contingency_priorities`, `test_mode_integration.test_rule_table_equivalent_to_legacy_logic` |
| SYS-AUT-005 | C2 bağlantı kaybı 30 s sürerse otomatik eve dönüş. | T | `test_modes` |

## 6. Sürü

| Kimlik | Gereksinim | Doğr. | Kod |
|---|---|---|---|
| SYS-SWM-001 | Her görev en fazla bir ajana atanmalı. | T | `test_swarm.test_each_task_at_most_once_and_energy_feasible` |
| SYS-SWM-002 | Hiçbir ajan rotası, %25 rezerv hariç enerji bütçesini aşmamalı. | T | aynı |
| SYS-SWM-003 | Dağıtım deterministik olmalı (aynı girdi → aynı çıktı; dağıtık uzlaşı için şart). | T | `test_swarm.test_deterministic` |
| SYS-SWM-004 | Ulaşılamayan görev atanmadan bırakılmalı ve operatöre bildirilmeli. | T | `test_swarm.test_unreachable_task_left_unassigned` |

## 7. Siber güvenlik ve düzenleyici

> Bu bölümdeki gereksinimler **planlanan** (planned) özelliklerdir; referans
> modelde uygulaması ve testi yoktur.

| Kimlik | Gereksinim | Doğr. | Kod |
|---|---|---|---|
| SYS-SEC-001 | Güvenli önyükleme: tüm yazılım imajları donanım güven kökü ile doğrulanmalı. | T | — |
| SYS-SEC-002 | Görev planları operatör anahtarıyla imzalı olmalı; imzasız plan yüklenemez. | T | — |
| SYS-SEC-003 | Tüm C2 trafiği kimlik doğrulamalı şifreleme (AEAD) ile korunmalı; tekrar saldırısına karşı sayaç. | T | — |
| SYS-REG-001 | ASTM F3411 uyumlu yayın tipi Remote ID. | T | — |
| SYS-REG-002 | EASA SORA / SHGM İHA talimatı kapsamında "spesifik" kategori operasyon dosyası. | I | — |

## 8. Simülasyon ve dijital ikiz

Bu gereksinimler yazılım simülasyonu içindir; uçuşa hazır yazılım
gereksinimi değildir. Doğrulama yöntemi tümünde T (test).

| Kimlik | Gereksinim | Uygulama | Kod (test) |
|---|---|---|---|
| SYS-SIM-001 | Merkezi, tek tip `VehicleState` (konum, hız, tutum, açısal hız, hava/yer hızı, irtifa, enerji, nav bütünlüğü, bağlantı, eyleyici sağlığı, mod, zaman) bulunmalı; RTA görünümü bundan türetilmeli. | `simurg/core/types.py` | `test_sim_state.test_derived_views`, `test_sim_state.test_envelope_view_from_central_state` |
| SYS-SIM-002 | Simülasyon adım sırası sabit, belgeli ve 14 adımlı olmalı. | `simurg/sim/engine.py` | `test_sim_engine.test_tick_order_documented_and_fixed` |
| SYS-SIM-003 | Aynı senaryo + yapılandırma + tohum birebir aynı son durumu, olay dizisini, metrikleri ve kaydı üretmeli; küresel rastgele durum kullanılmamalı. | `simurg/sim/engine.py` | `test_sim_engine.test_same_seed_same_result`, `test_sim_engine.test_different_seed_different_noise` |
| SYS-SIM-004 | 6-DOF dinamik `durum + kuvvet + moment -> türev` biçiminde olmalı; integratör değiştirilebilir (RK4, Euler); NaN/Inf yakalanmalı. | `simurg/sim/dynamics.py` | `test_dynamics.test_rk4_more_accurate_than_euler`, `test_dynamics.test_integrator_registry_and_nan_guard`, `test_dynamics.test_torque_free_rotation_preserves_energy` |
| SYS-SIM-005 | Aerodinamik model bir arayüz arkasında olmalı; analitik ve tablo tabanlı modeller ızgara noktalarında eşdeğer olmalı; ±180° hücum açısında sonlu çıktı. | `simurg/aero/model.py` | `test_dynamics.test_table_model_matches_analytic_on_grid`, `test_dynamics.test_full_range_alpha_is_finite` |
| SYS-SIM-006 | Kontrol etkinliği uçuş rejimine bağlı olmalı (askı/geçiş/seyir); askı rejimi v0.1 matrisiyle birebir aynı olmalı. | `simurg/control/effectiveness.py` | `test_effectiveness.test_hover_regime_identical_to_legacy`, `test_effectiveness.test_cruise_regime_folds_inner_motors_and_boosts_elevons` |
| SYS-SIM-007 | Geçiş koordinatörü mod makinesinden ayrı olmalı; irtifa kaybı, zaman aşımı, sürekli doyma ve yunuslama takip hatasında geçişi iptal etmeli. | `simurg/control/transition.py` | `test_effectiveness.test_abort_on_altitude_loss_and_timeout`, `test_effectiveness.test_abort_on_persistent_saturation` |
| SYS-SIM-008 | Eyleyici modeli gecikme, birinci derece tepki, doyma ve DEGRADED/STUCK/OFFLINE arızalarını temsil etmeli; nominal (beklenen) tepki arızadan etkilenmemeli. | `simurg/sim/actuators.py` | `test_actuators.test_degraded_stuck_offline_and_clear`, `test_actuators.test_latency_delays_command` |
| SYS-SIM-009 | Arızalar simülasyon zamanına bağlı, meta verili (kimlik, başlangıç, süre, hedef, şiddet, açıklama), doğrulanmış ve tekrarlanabilir biçimde uygulanmalı. | `simurg/sim/faults.py` | `test_faults.test_activation_on_first_tick_at_or_after_start`, `test_faults.test_validation`, `test_faults.test_reproducible`, `test_sim_engine.test_fault_activation_reproducible` |
| SYS-SIM-010 | Sensör modeli gürültü, bias, dropout, sağlık, zaman damgası ve kalite taşımalı; arıza RNG akışını değiştirmemeli. | `simurg/sim/sensors.py` | `test_faults.test_same_seed_same_measurements_and_dropout_keeps_stream`, `test_faults.test_bias_and_suite_routing` |
| SYS-SIM-011 | Navigasyon `NavigationSolution` döndürmeli; bütünlük için >= 2 kaynak gerekmeli; kaynak yokken ataletsel ilerletme ve büyüyen koruma seviyesi. | `simurg/nav/providers.py` | `test_nav_solution.test_single_source_cannot_be_verified`, `test_nav_solution.test_no_source_inertial_propagation_with_growing_pl`, `test_nav_solution.test_biased_source_rejected` |
| SYS-SIM-012 | RTA kararı açıklanabilir meta veri içermeli (seçilen kaynak, gerekçeler, mevcut/öngörülen ihlaller, kilit, ufuk, zaman). | `simurg/safety/rta.py` | `test_rta_integration.test_decision_metadata_on_intervention`, `test_rta_integration.test_latch_metadata` |
| SYS-SIM-013 | RTA'nın v0.1 `select` API'si korunmalı ve yeni `decide` ile aynı kararı vermeli; kestirici enjekte edilebilir olmalı. | `simurg/safety/rta.py` | `test_rta_integration.test_select_is_backward_compatible_with_decide`, `test_rta_integration.test_custom_predictor_injection` |
| SYS-SIM-014 | FDIR çıktıları ortak `ComponentHealth` biçiminde olmalı (NOMINAL/DEGRADED/FAILED/UNKNOWN); gözlenemeyen bileşen UNKNOWN. | `simurg/fdir/monitor.py` | `test_fdir_integration.test_reports_standard_format_and_unknown_when_unobserved` |
| SYS-SIM-015 | Nominal uçuşta FDIR yanlış alarm üretmemeli; tek motor verim kaybı < 1 s'de tespit edilip dağıtıcıya sağlık olarak yansımalı. | `simurg/sim/engine.py` | `test_fdir_integration.test_no_false_alarms_in_nominal_flight`, `test_fdir_integration.test_degraded_motor_detected_and_fed_to_allocation` |
| SYS-SIM-016 | Her mod geçiş isteği kaynak, hedef, gerekçe, koruma sonucu ve zaman ile kaydedilmeli; v0.1 `request()` korunmalı. | `simurg/modes/flight_modes.py` | `test_mode_integration.test_invalid_transition_diagnostics`, `test_mode_integration.test_request_keeps_bool_api_and_table_is_single_source` |
| SYS-SIM-017 | Acil durum öncelik tablosu tek kaynak olmalı; v0.1 mantığıyla eşdeğer ve docs/08 tablosuyla aynı olmalı; kararlar `ContingencyDecision` olarak üretilmeli. | `simurg/modes/flight_modes.py` | `test_mode_integration.test_rule_table_equivalent_to_legacy_logic`, `test_mode_integration.test_docs_table_matches_code`, `test_mode_integration.test_decision_object` |
| SYS-SIM-018 | Enerji alt sistemi SI birimli `EnergyState` döndürmeli; bozunum rezerv ve eve dönüş kararına yansımalı; bozunum modeli enjekte edilebilir olmalı. | `simurg/power/energy_manager.py` | `test_energy_state.test_state_fields_si_units`, `test_energy_state.test_degradation_propagates_to_reserve_and_rth`, `test_energy_state.test_degradation_model_injection` |
| SYS-SIM-019 | Kayıt olayları kayıpsız tutmalı; JSON şeması adlı ve sürümlü olmalı; bilinmeyen şema reddedilmeli. | `simurg/sim/recorder.py` | `test_recorder.test_events_never_dropped_and_snapshots_periodic`, `test_recorder.test_schema_and_json_roundtrip`, `test_recorder.test_load_rejects_unknown_schema` |
| SYS-SIM-020 | Tekrar oynatma olay sırasını korumalı; mod, RTA, sağlık ve arıza geçmişlerini sunmalı. | `simurg/sim/replay.py` | `test_replay.test_event_ordering_preserved`, `test_replay.test_histories`, `test_replay.test_health_history` |
| SYS-SIM-021 | Standart metrikler (müdahale, tespit gecikmesi, en küçük güvenlik payı, enerji, doyma oranı ...) üretilmeli. | `simurg/sim/metrics.py` | `test_metrics.test_detection_latency_matching_rules`, `test_metrics.test_compute_counts`, `test_metrics.test_combined_scenario_metrics` |
| SYS-SIM-022 | Monte Carlo her koşunun tohumunu kaydetmeli; başarısız koşu yalnızca tohumuyla birebir yeniden üretilebilmeli. | `simurg/sim/montecarlo.py` | `test_monte_carlo.test_campaign_and_reproduction`, `test_monte_carlo.test_seeds_and_params_are_reproducible` |
| SYS-SIM-023 | Hazır senaryo kütüphanesinin her senaryosu beklenen güvenlik sonuçlarını üretmeli, çarpma olmamalı. | `simurg/sim/scenarios.py` | `test_sim_engine.test_all_library_scenarios_meet_expectations` |
| SYS-SIM-024 | Simülasyonda C2 kaybı 30 s'yi aştığında (bir adım içinde) eve dönüş tetiklenmeli. | `simurg/sim/engine.py` | `test_mode_integration.test_link_loss_return_after_30_s` |
| SYS-SIM-025 | Simülasyonda nav bütünlüğü kaybı LOITER_HOLD'a, geri geldiğinde göreve devama yol açmalı. | `simurg/sim/engine.py` | `test_mode_integration.test_nav_integrity_loss_loiters_then_resumes` |
| SYS-SIM-026 | Enerji uyarısı görevi iptal edip eve dönüşü başlatmalı. | `simurg/sim/engine.py` | `test_energy_state.test_reserve_warning_aborts_mission_and_lands` |
| SYS-SIM-028 | Simülasyonda hover kabiliyeti kaybı sabit kanatla acil inişe, sürekli kontrol kaybı (tutum hatası ya da dağıtıcı moment açığı) paraşüte yol açmalı; ikisi de çarpmasız bitmeli. | `simurg/sim/engine.py` | `test_mode_integration.test_hover_loss_glides_and_control_loss_deploys_parachute` |
| SYS-SIM-029 | Nominal uçuşta RTA yumuşak zarfına en küçük normalize pay > 0,1 olmalı (geçiş tamamlanma eşiği zarfın içinde). | `simurg/control/transition.py` | `test_rta_integration.test_nominal_flight_has_no_rta_intervention` |
| SYS-SIM-030 | YZ/gelişmiş kontrolcü nihai uçuş yetkisi olamaz: kontrol katmanı yalnızca RTA'nın ürettiği (taklit edilemez) `ValidatedCommand`'ı kabul etmeli; YZ katmanının eyleyiciye içe aktarma yolu olmamalı; hatalı YZ önerisi aracı sert zarf dışına çıkaramamalı. | `simurg/safety/rta.py`, `simurg/sim/vehicle_control.py` | `test_safety_invariants.test_validated_command_cannot_be_forged`, `test_safety_invariants.test_controller_rejects_unvalidated_command`, `test_safety_invariants.test_ai_layer_has_no_import_path_to_actuation`, `test_safety_invariants.test_ai_cannot_drive_vehicle_outside_hard_envelope` |
| SYS-SIM-031 | Mod değişmezleri: PARACHUTE havada terminal; havadaki araç DISARMED olamaz; mod değişimi yalnızca geçiş tablosuyla. | `simurg/modes/flight_modes.py` | `test_safety_invariants.test_parachute_mode_is_terminal_in_air`, `test_safety_invariants.test_airborne_vehicle_cannot_disarm`, `test_safety_invariants.test_mode_changes_only_through_transition_table` |
| SYS-SIM-032 | RTA değişmezleri: kilitliyken gelişmiş çıktı seçilemez; sert ihlalde yetki verilmez; sonlu olmayan durum güvenli sayılmaz. | `simurg/safety/rta.py` | `test_safety_invariants.test_rta_latched_never_selects_advanced`, `test_safety_invariants.test_hard_envelope_violation_denies_advanced_authority`, `test_safety_invariants.test_nonfinite_state_is_not_treated_as_safe` |
| SYS-SIM-033 | Fail-safe: bilinmeyen sağlık, navigasyon, ölçüm ve enerji durumları sağlıklı kabul edilmemeli; kritik ölçüm kaybında açık geri dönüş ve olay; durum bozulmasında `sim_failed` + `SimulationError`. | `simurg/sim/health.py`, `simurg/sim/airdata.py`, `simurg/nav/providers.py`, `simurg/power/reserve.py` | `test_failsafe.test_unobserved_motors_are_not_counted_for_hover_when_airborne`, `test_failsafe.test_navigation_without_solution_never_reports_integrity`, `test_failsafe.test_airspeed_loss_uses_explicit_fallback_and_is_reported`, `test_failsafe.test_state_corruption_is_a_simulation_error_not_silent` |
| SYS-SIM-034 | Güvenlikle ilgili her olay `reason` (bileşen olayları ayrıca `component`) taşımalı; mod, RTA, nav, FDIR, arıza, enerji, geçiş ve görev sonucu kararları kayıttan açıklanabilmeli. | `simurg/sim/engine.py`, `simurg/sim/replay.py` | `test_explainability.test_safety_events_carry_reason_and_component`, `test_explainability.test_why_did_mode_become_return`, `test_explainability.test_why_mission_was_not_completed` |
| SYS-SIM-035 | Zaman ve sıra değişmezleri: olay zamanları geriye gitmez, anlık görüntü zamanları kesin artan, replay sırayı değiştirmez. | `simurg/sim/recorder.py` | `test_safety_invariants.test_event_timestamps_and_simulation_time_never_go_backwards`, `test_safety_invariants.test_replay_does_not_reorder_events` |
| SYS-SIM-036 | Paket: tek sürüm kaynağı, yalnızca NumPy çalışma bağımlılığı, CI'da Python 3.10–3.12, kodda gizli bilgi ve ağ bağımlılığı yok. | `pyproject.toml`, `.github/workflows/tests.yml` | `test_packaging.test_version_single_source_and_semver`, `test_packaging.test_runtime_dependencies_minimal`, `test_packaging.test_ci_runs_unittest_on_supported_pythons`, `test_packaging.test_no_hardcoded_secrets`, `test_packaging.test_library_has_no_network_dependencies` |
| SYS-SIM-027 | Kütüphane kodu varsayılan olarak terminale yazmamalı (logging, NullHandler); alan hataları özel istisnalarla bildirilmeli. | `simurg/__init__.py` | `test_cli.test_library_logger_is_silent`, `test_cli.test_unknown_scenario_is_domain_error` |
