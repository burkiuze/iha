# 08 — FAILURE / CONTINGENCY FLOW

> Sivil mühendislik referans mimarisi — yazılım/güvenlik/simülasyon düzeyi.
> Uçuşa hazır donanım, kablolama, ESC/motor ayarı ya da kontrol kazancı içermez.
> Ana belge: [15 — Master System Architecture](../15-sistem-mimarisi.md).
> Diyagram ve tablolar `python -m simurg.architecture --update-all` ile üretilir.

## Arıza zincirleri

Her zincir `FAULT → DETECTION → ISOLATION → DEGRADATION → CONTINGENCY →
EVENT / RECORD` aşamalarını gösterir; olay listesi adı geçen kütüphane
senaryosunda `tests/test_architecture.py` ile doğrulanır.

<!-- BEGIN GENERATED: failure-chains -->
**Sensor loss** — senaryo `nav_source_loss`: Kalan 3 kaynakla bütünlük korunur; görev tamamlanır

```mermaid
flowchart LR
  classDef fault fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  classDef record fill:#ddf4ff,stroke:#0969da,color:#0a3069;
  F["FAULT<br/>GNSS ölçümü kesilir (sensor_dropout)"]:::fault
  D["DETECTION<br/>Signal Validation<br/>Sensor Health"]:::stage
  I["ISOLATION<br/>Navigation Source Manager<br/>Sensor FDIR"]:::stage
  G["DEGRADATION<br/>NavigationHealth"]:::stage
  C["CONTINGENCY<br/>System Supervisor"]:::stage
  E["EVENT / RECORD<br/>sensor_health_changed<br/>nav_source_unavailable<br/>vehicle_health_changed"]:::record
  F --> D --> I --> G --> C --> E
```

**Navigation loss** — senaryo `nav_integrity_loss`: LOITER_HOLD; bütünlük dönünce görev sürer

```mermaid
flowchart LR
  classDef fault fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  classDef record fill:#ddf4ff,stroke:#0969da,color:#0a3069;
  F["FAULT<br/>GNSS + VIO 40 s yok"]:::fault
  D["DETECTION<br/>Navigation Source Manager<br/>Integrity Monitor"]:::stage
  I["ISOLATION<br/>Fault Exclusion<br/>Navigation FDIR"]:::stage
  G["DEGRADATION<br/>Inertial Propagation<br/>NavigationHealth"]:::stage
  C["CONTINGENCY<br/>Contingency Manager<br/>Flight Mode Machine"]:::stage
  E["EVENT / RECORD<br/>nav_integrity_lost<br/>contingency<br/>mode_transition<br/>nav_integrity_restored"]:::record
  F --> D --> I --> G --> C --> E
```

**FCC lane disagreement** — senaryo `fcc_lane_divergence`: B yalıtılır; A + C ile ikili mod; görev tamamlanır

```mermaid
flowchart LR
  classDef fault fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  classDef record fill:#ddf4ff,stroke:#0969da,color:#0a3069;
  F["FAULT<br/>Şerit B çıktısı sapar"]:::fault
  D["DETECTION<br/>Cross-Lane Comparator<br/>Divergence Detection"]:::stage
  I["ISOLATION<br/>Lane Isolation Manager"]:::stage
  G["DEGRADATION<br/>Lane Voter<br/>FCC FDIR"]:::stage
  C["CONTINGENCY<br/>Vehicle Health Manager<br/>System Supervisor"]:::stage
  E["EVENT / RECORD<br/>fcc_lane_state_changed<br/>vehicle_health_changed"]:::record
  F --> D --> I --> G --> C --> E
```

**FCC lane loss** — senaryo `fcc_lane_loss`: A FAILED; ikili mod; görev tamamlanır

```mermaid
flowchart LR
  classDef fault fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  classDef record fill:#ddf4ff,stroke:#0969da,color:#0a3069;
  F["FAULT<br/>Şerit A kalp atışı kesilir"]:::fault
  D["DETECTION<br/>Watchdog"]:::stage
  I["ISOLATION<br/>Lane Isolation Manager"]:::stage
  G["DEGRADATION<br/>Lane Voter<br/>FCC FDIR"]:::stage
  C["CONTINGENCY<br/>Vehicle Health Manager<br/>System Supervisor"]:::stage
  E["EVENT / RECORD<br/>fcc_lane_state_changed<br/>vehicle_health_changed"]:::record
  F --> D --> I --> G --> C --> E
```

**Motor degradation** — senaryo `single_actuator_degradation`: Sağlık ağırlıklı dağıtım; görev tamamlanır

```mermaid
flowchart LR
  classDef fault fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  classDef record fill:#ddf4ff,stroke:#0969da,color:#0a3069;
  F["FAULT<br/>M2U %30 itki kaybı"]:::fault
  D["DETECTION<br/>Motor Monitor (CUSUM)"]:::stage
  I["ISOLATION<br/>Motor Health<br/>Motor FDIR"]:::stage
  G["DEGRADATION<br/>Health-Aware Allocation"]:::stage
  C["CONTINGENCY<br/>Vehicle Health Manager<br/>System Supervisor"]:::stage
  E["EVENT / RECORD<br/>fdir_warning<br/>vehicle_health_changed"]:::record
  F --> D --> I --> G --> C --> E
```

**Actuator failure** — senaryo `hover_capability_loss`: Hover yok -> EMERGENCY_LAND (süzülerek)

```mermaid
flowchart LR
  classDef fault fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  classDef record fill:#ddf4ff,stroke:#0969da,color:#0a3069;
  F["FAULT<br/>M1U + M1L seyirde devre dışı"]:::fault
  D["DETECTION<br/>Motor Monitor (CUSUM)"]:::stage
  I["ISOLATION<br/>Motor FDIR<br/>Actuator Health Gate"]:::stage
  G["DEGRADATION<br/>Available Authority"]:::stage
  C["CONTINGENCY<br/>Contingency Manager<br/>Flight Mode Machine"]:::stage
  E["EVENT / RECORD<br/>fdir_failure<br/>actuator_excluded<br/>contingency<br/>touchdown"]:::record
  F --> D --> I --> G --> C --> E
```

**Power degradation** — senaryo `energy_reserve_warning`: Görev iptali -> RETURN

```mermaid
flowchart LR
  classDef fault fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  classDef record fill:#ddf4ff,stroke:#0969da,color:#0a3069;
  F["FAULT<br/>Batarya kapasitesi yarıya iner (FC yok)"]:::fault
  D["DETECTION<br/>Reserve Estimator"]:::stage
  I["ISOLATION<br/>Energy FDIR"]:::stage
  G["DEGRADATION<br/>Energy Manager"]:::stage
  C["CONTINGENCY<br/>Mission Manager<br/>Flight Mode Machine"]:::stage
  E["EVENT / RECORD<br/>energy_warning<br/>mission_abort<br/>mode_transition"]:::record
  F --> D --> I --> G --> C --> E
```

**Communication loss** — senaryo `communication_loss`: 30 s sonra RETURN

```mermaid
flowchart LR
  classDef fault fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  classDef record fill:#ddf4ff,stroke:#0969da,color:#0a3069;
  F["FAULT<br/>C2 kalıcı kopar"]:::fault
  D["DETECTION<br/>Heartbeat Monitor"]:::stage
  I["ISOLATION<br/>Link Health<br/>Communication FDIR"]:::stage
  G["DEGRADATION<br/>System Supervisor"]:::stage
  C["CONTINGENCY<br/>Contingency Manager<br/>Flight Mode Machine"]:::stage
  E["EVENT / RECORD<br/>link_lost<br/>contingency<br/>mode_transition"]:::record
  F --> D --> I --> G --> C --> E
```

**Mission computer failure** — senaryo `mission_computer_failure`: Bayat öneri RTA'ya ulaşmaz; güvenlik kontrolcüsü; akış düzelince görev sürer

```mermaid
flowchart LR
  classDef fault fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  classDef record fill:#ddf4ff,stroke:#0969da,color:#0a3069;
  F["FAULT<br/>Öneri 6 s donar (bayat)"]:::fault
  D["DETECTION<br/>Timestamp / Freshness"]:::stage
  I["ISOLATION<br/>Command Validator<br/>Mission Computer FDIR"]:::stage
  G["DEGRADATION<br/>Safety Controller<br/>Command Selector"]:::stage
  C["CONTINGENCY<br/>Vehicle Health Manager<br/>System Supervisor"]:::stage
  E["EVENT / RECORD<br/>command_rejected<br/>vehicle_health_changed<br/>command_accepted"]:::record
  F --> D --> I --> G --> C --> E
```

**RTA intervention** — senaryo `rta_intervention`: SC devralır; histerezis sonrası AC'ye dönüş; görev tamamlanır

```mermaid
flowchart LR
  classDef fault fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  classDef record fill:#ddf4ff,stroke:#0969da,color:#0a3069;
  F["FAULT<br/>Gelişmiş kontrolcü 75° yatış önerir"]:::fault
  D["DETECTION<br/>State Predictor<br/>Predicted Violation Check"]:::stage
  I["ISOLATION<br/>Command Selector"]:::stage
  G["DEGRADATION<br/>Safety Controller"]:::stage
  C["CONTINGENCY<br/>Recovery Hysteresis"]:::stage
  E["EVENT / RECORD<br/>rta_intervention<br/>rta_recovery"]:::record
  F --> D --> I --> G --> C --> E
```
<!-- END GENERATED: failure-chains -->

## Contingency Manager

Girdiler: Vehicle Health, Navigation Integrity, Energy Status, Control
Authority, Communication Health, RTA State. Çıktı (`ContingencyDecision`):
**Recommended Safe Mode, Reason, Priority, Timestamp** + karar anındaki
girdi görüntüsü. Mod değişimi yalnızca Flight Mode Machine üzerinden
(koruma koşullarıyla) yapılır. Kural tablosu docs/08 §3 ile eşleşir; araç
sağlığı seviyesi ve RTA kilidi bugün kayıtlı girdidir, kural tetikleyicisi değil.

## Sistem durumu

```mermaid
stateDiagram-v2
  [*] --> NORMAL
  NORMAL --> DEGRADED: sağlık ≠ NOMINAL / RTA güvenlik kaynağında / enerji uyarısı / geçersiz öneri
  DEGRADED --> CONTINGENCY: acil durum modu / RTA kilidi / nav, C2 kaybı / sağlık CONTINGENCY
  CONTINGENCY --> EMERGENCY: acil iniş · paraşüt / kontrol kaybı / sağlık CRITICAL
  DEGRADED --> NORMAL
  CONTINGENCY --> DEGRADED
```

System Supervisor yalnızca değerlendirir; **eyleyici sürmez, mod değiştirmez**.

## Diyagram

<!-- BEGIN GENERATED: view-mode-supervision -->
```mermaid
flowchart LR
  classDef implemented fill:#d7f5dd,stroke:#1a7f37,color:#0b3d1a;
  classDef partial fill:#fff4c2,stroke:#9a6700,color:#3d2e00;
  classDef unvalidated fill:#ffe1c7,stroke:#bc4c00,color:#4d1f00;
  classDef planned fill:#eef0f3,stroke:#8c959f,color:#57606a,stroke-dasharray: 4 3;
  classDef gate fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a,stroke-width:3px;
  classDef ext fill:#ffffff,stroke:#8c959f,color:#57606a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  subgraph MODE["MODE / CONTINGENCY MANAGEMENT"]
    direction TB
    MD_FSM["Flight Mode Machine"]:::gate
    MD_TABLE["Transition Table"]:::implemented
    MD_CONTINGENCY["Contingency Manager"]:::implemented
    MD_RULES["Contingency Rule Table"]:::implemented
    MD_INPUTS["Contingency Input Snapshot"]:::implemented
  end
  subgraph PRE["PREFLIGHT SUPERVISOR"]
    direction TB
    PRE_SUPERVISOR["Preflight Supervisor"]:::implemented
    PF_CONFIG["Configuration Check"]:::implemented
    PF_SENSOR["Sensor Check"]:::implemented
    PF_NAV["Navigation Check"]:::implemented
    PF_FCC["FCC Lane Check"]:::implemented
    PF_RTA["RTA Check"]:::implemented
    PF_CTRL["Control Authority Check"]:::implemented
    PF_ACT["Actuator Health Check"]:::implemented
    PF_ENERGY["Energy Check"]:::implemented
    PF_COMM["Communication Check"]:::implemented
    PF_MISSION["Mission Validation"]:::implemented
    PF_REC["Recorder Check"]:::implemented
  end
  subgraph SUP["SYSTEM SUPERVISION"]
    direction TB
    SUP_SYSTEM["System Supervisor"]:::implemented
  end
  CO_CMD_ROUTER["Command Router<br/><i>COMMUNICATION</i>"]:::ext
  MC_MISSION_MGR["Mission Manager<br/><i>MISSION COMPUTER (yalnızca öneri; uçuş-kritik değil)</i>"]:::ext
  CV_MODE["Mode Compatibility<br/><i>COMMAND VALIDATION</i>"]:::ext
  RTA_SELECTOR["Command Selector<br/><i>RUNTIME ASSURANCE (Simplex)</i>"]:::ext
  C_MODE_SEL["Control Law Selector<br/><i>FLIGHT CONTROL (yazılım soyutlaması; kazanç içermez)</i>"]:::ext
  AV_PARACHUTE["Recovery Parachute<br/><i>AIR VEHICLE (parametrik model)</i>"]:::ext
  BUS_HEALTH["Health Bus<br/><i>DATA BUS (mantıksal)</i>"]:::ext
  EN_EMERGENCY["Emergency Energy State<br/><i>POWER / ENERGY</i>"]:::ext
  EN_RESERVE["Reserve Estimator<br/><i>POWER / ENERGY</i>"]:::ext
  NAV_HEALTH["NavigationHealth<br/><i>NAVIGATION</i>"]:::ext
  CO_LINK_HEALTH["Link Health<br/><i>COMMUNICATION</i>"]:::ext
  AL_AUTHORITY["Available Authority<br/><i>CONTROL ALLOCATION</i>"]:::ext
  BUS_STATE["State Bus<br/><i>DATA BUS (mantıksal)</i>"]:::ext
  FDR_MODE["Mode Recorder<br/><i>FLIGHT DATA RECORDER</i>"]:::ext
  GUID["GUIDANCE"]:::ext
  CFG_MANAGER["Configuration Manager<br/><i>CONFIGURATION</i>"]:::ext
  SEN_HEALTH["Sensor Health<br/><i>SENSOR SUITE</i>"]:::ext
  NAV_SRC_MGR["Navigation Source Manager<br/><i>NAVIGATION</i>"]:::ext
  FCC_C_WATCHDOG["Watchdog<br/><i>TRIPLEX FLIGHT COMPUTERS</i>"]:::ext
  RTA_SELFTEST["RTA Self-Test<br/><i>RUNTIME ASSURANCE (Simplex)</i>"]:::ext
  ACT_FEEDBACK["Actuator Feedback<br/><i>ACTUATOR SYSTEM (simülasyon soyutlaması)</i>"]:::ext
  EN_MANAGER["Energy Manager<br/><i>POWER / ENERGY</i>"]:::ext
  GCS_MISSION_PLAN["Mission Planning<br/><i>GROUND SEGMENT</i>"]:::ext
  FDR_CORE["Flight Data Recorder<br/><i>FLIGHT DATA RECORDER</i>"]:::ext
  FDIR_SUP["FDIR Supervisor<br/><i>FDIR</i>"]:::ext
  BUS_EVENT["Event Bus<br/><i>DATA BUS (mantıksal)</i>"]:::ext
  BUS_TLM["Telemetry Bus<br/><i>DATA BUS (mantıksal)</i>"]:::ext
  CFG_SAFETY["Safety Configuration<br/><i>CONFIGURATION</i>"]:::ext
  CO_CMD_ROUTER ==>|"operatör mod isteği"| MD_FSM
  MC_MISSION_MGR ==>|"nominal mod isteği"| MD_FSM
  MD_FSM -.->|"aktif mod"| CV_MODE
  RTA_SELECTOR -.->|"RTA durumu"| MD_CONTINGENCY
  RTA_SELECTOR -.->|"RTA durumu"| SUP_SYSTEM
  MD_FSM -.->|"aktif mod"| C_MODE_SEL
  MD_FSM -.->|"PARACHUTE modu"| AV_PARACHUTE
  BUS_HEALTH -.->|"araç sağlığı"| MD_CONTINGENCY
  BUS_HEALTH -.->|"araç sağlığı"| SUP_SYSTEM
  MD_FSM -.->|"acil mod"| EN_EMERGENCY
  EN_RESERVE -.->|"eve dönüş/iniş enerjisi"| MD_CONTINGENCY
  EN_RESERVE -.->|"enerji uyarısı"| SUP_SYSTEM
  MD_TABLE -.->|"izinli geçişler"| MD_FSM
  MD_RULES -.->|"öncelikli kurallar"| MD_CONTINGENCY
  NAV_HEALTH -.->|"nav bütünlüğü"| MD_CONTINGENCY
  CO_LINK_HEALTH -.->|"C2 kesinti süresi"| MD_CONTINGENCY
  AL_AUTHORITY -.->|"hover fizibilitesi"| MD_CONTINGENCY
  MD_INPUTS -.-> MD_CONTINGENCY
  MD_CONTINGENCY -.->|"önerilen güvenli mod"| MD_FSM
  MD_FSM -->|"aktif mod"| BUS_STATE
  MD_FSM --> FDR_MODE
  MD_FSM -.->|"mod -> güdüm seçimi"| GUID
  MD_FSM -.->|"uçuş modu"| SUP_SYSTEM
  PF_CONFIG -.-> PRE_SUPERVISOR
  PF_SENSOR -.-> PRE_SUPERVISOR
  PF_NAV -.-> PRE_SUPERVISOR
  PF_FCC -.-> PRE_SUPERVISOR
  PF_RTA -.-> PRE_SUPERVISOR
  PF_CTRL -.-> PRE_SUPERVISOR
  PF_ACT -.-> PRE_SUPERVISOR
  PF_ENERGY -.-> PRE_SUPERVISOR
  PF_COMM -.-> PRE_SUPERVISOR
  PF_MISSION -.-> PRE_SUPERVISOR
  PF_REC -.-> PRE_SUPERVISOR
  CFG_MANAGER -.-> PF_CONFIG
  SEN_HEALTH -.-> PF_SENSOR
  NAV_SRC_MGR -.->|"kaynak sayısı"| PF_NAV
  FCC_C_WATCHDOG -.->|"kalp atışları"| PF_FCC
  RTA_SELFTEST -.->|"öz-test"| PF_RTA
  AL_AUTHORITY -.->|"hover marjı"| PF_CTRL
  ACT_FEEDBACK -.->|"BIT"| PF_ACT
  EN_MANAGER -.->|"kullanılabilir enerji"| PF_ENERGY
  CO_LINK_HEALTH -.-> PF_COMM
  GCS_MISSION_PLAN -.->|"görev"| PF_MISSION
  FDR_CORE -.->|"kayıt alınıyor"| PF_REC
  PRE_SUPERVISOR -.->|"preflight_ok -> ARMED"| MD_FSM
  NAV_HEALTH -.->|"nav bütünlüğü"| SUP_SYSTEM
  CO_LINK_HEALTH -.->|"haberleşme"| SUP_SYSTEM
  FDIR_SUP -.->|"FDIR raporları"| SUP_SYSTEM
  SUP_SYSTEM -->|"system_state_changed"| BUS_EVENT
  SUP_SYSTEM -->|"sistem durumu"| BUS_TLM
  CFG_SAFETY -->|"eşikler"| MD_CONTINGENCY
```
<!-- END GENERATED: view-mode-supervision -->

## Bileşen matrisi

<!-- BEGIN GENERATED: matrix-mode-supervision -->
#### MODE / CONTINGENCY MANAGEMENT

| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | Code Location | Implementation Status |
|---|---|---|---|---|---|---|---|
| **Flight Mode Machine** `MD_FSM` *(geçit)* | 13 mod; mod DEĞİŞİMİNİN TEK YOLU (yetki geçidi) | mod istekleri, bağlam | aktif mod, TransitionRecord | durumsuz (n/a) | Tablo dışı / koruması sağlanmayan istek reddedilir + MODE_REJECTED | `simurg/modes/flight_modes.py::FlightModeMachine` | IMPLEMENTED |
| **Transition Table** `MD_TABLE` | Geçiş + koruma koşulları (tek kaynak) | - | izinli geçişler | durumsuz (n/a) | PARACHUTE havada terminal | `simurg/modes/flight_modes.py::TRANSITIONS` | IMPLEMENTED |
| **Contingency Manager** `MD_CONTINGENCY` | Önerilen güvenli mod + gerekçe + öncelik + zaman | araç sağlığı, nav bütünlüğü, enerji, kontrol otoritesi, haberleşme, RTA | ContingencyDecision | durumsuz (n/a) | İstek FSM korumasına tabidir; reddedilirse alt kurala inilmez | `simurg/modes/flight_modes.py::ContingencyManager` | IMPLEMENTED — Sağlık seviyesi ve RTA kilidi kayıtlı girdi; kural tetikleyicisi değil |
| **Contingency Rule Table** `MD_RULES` | Öncelikli kurallar (docs/08 §3) | - | kurallar | durumsuz (n/a) | n/a | `simurg/modes/flight_modes.py::CONTINGENCY_RULES` | IMPLEMENTED |
| **Contingency Input Snapshot** `MD_INPUTS` | Kararla birlikte kaydedilen girdiler | Context | inputs | durumsuz (n/a) | n/a | `simurg/modes/flight_modes.py::CONTINGENCY_INPUTS` | IMPLEMENTED |

#### PREFLIGHT SUPERVISOR

| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | Code Location | Implementation Status |
|---|---|---|---|---|---|---|---|
| **Preflight Supervisor** `PRE_SUPERVISOR` | 11 kontrol; kritik başarısızlıkta ARMED yok | kontrol sonuçları | PreflightReport, preflight_ok | geçti/kaldı | Bilinmeyen durum geçmiş sayılmaz; PREFLIGHT_FAILED + kalkış yok | `simurg/sim/preflight.py::PreflightSupervisor` | IMPLEMENTED |
| **Configuration Check** `PF_CONFIG` | Uçuş öncesi: Configuration Check | ilgili alt sistem durumu | PreflightCheck | geçti/kaldı + gerekçe | Kritik: başarısızsa ARMED yok | `simurg/sim/preflight.py::CHECK_NAMES` | IMPLEMENTED |
| **Sensor Check** `PF_SENSOR` | Uçuş öncesi: Sensor Check | ilgili alt sistem durumu | PreflightCheck | geçti/kaldı + gerekçe | Kritik: başarısızsa ARMED yok | `simurg/sim/preflight.py::CHECK_NAMES` | IMPLEMENTED |
| **Navigation Check** `PF_NAV` | Uçuş öncesi: Navigation Check | ilgili alt sistem durumu | PreflightCheck | geçti/kaldı + gerekçe | Kritik: başarısızsa ARMED yok | `simurg/sim/preflight.py::CHECK_NAMES` | IMPLEMENTED |
| **FCC Lane Check** `PF_FCC` | Uçuş öncesi: FCC Lane Check | ilgili alt sistem durumu | PreflightCheck | geçti/kaldı + gerekçe | Kritik: başarısızsa ARMED yok | `simurg/sim/preflight.py::CHECK_NAMES` | IMPLEMENTED |
| **RTA Check** `PF_RTA` | Uçuş öncesi: RTA Check | ilgili alt sistem durumu | PreflightCheck | geçti/kaldı + gerekçe | Kritik: başarısızsa ARMED yok | `simurg/sim/preflight.py::CHECK_NAMES` | IMPLEMENTED |
| **Control Authority Check** `PF_CTRL` | Uçuş öncesi: Control Authority Check | ilgili alt sistem durumu | PreflightCheck | geçti/kaldı + gerekçe | Kritik: başarısızsa ARMED yok | `simurg/sim/preflight.py::CHECK_NAMES` | IMPLEMENTED |
| **Actuator Health Check** `PF_ACT` | Uçuş öncesi: Actuator Health Check | ilgili alt sistem durumu | PreflightCheck | geçti/kaldı + gerekçe | Kritik: başarısızsa ARMED yok | `simurg/sim/preflight.py::CHECK_NAMES` | IMPLEMENTED |
| **Energy Check** `PF_ENERGY` | Uçuş öncesi: Energy Check | ilgili alt sistem durumu | PreflightCheck | geçti/kaldı + gerekçe | Kritik: başarısızsa ARMED yok | `simurg/sim/preflight.py::CHECK_NAMES` | IMPLEMENTED |
| **Communication Check** `PF_COMM` | Uçuş öncesi: Communication Check | ilgili alt sistem durumu | PreflightCheck | geçti/kaldı + gerekçe | Kritik: başarısızsa ARMED yok | `simurg/sim/preflight.py::CHECK_NAMES` | IMPLEMENTED |
| **Mission Validation** `PF_MISSION` | Uçuş öncesi: Mission Validation | ilgili alt sistem durumu | PreflightCheck | geçti/kaldı + gerekçe | Kritik: başarısızsa ARMED yok | `simurg/sim/preflight.py::CHECK_NAMES` | IMPLEMENTED |
| **Recorder Check** `PF_REC` | Uçuş öncesi: Recorder Check | ilgili alt sistem durumu | PreflightCheck | geçti/kaldı + gerekçe | Kritik: başarısızsa ARMED yok | `simurg/sim/preflight.py::CHECK_NAMES` | IMPLEMENTED |

#### SYSTEM SUPERVISION

| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | Code Location | Implementation Status |
|---|---|---|---|---|---|---|---|
| **System Supervisor** `SUP_SYSTEM` | NORMAL/DEGRADED/CONTINGENCY/EMERGENCY; EYLEYİCİ SÜRMEZ | araç sağlığı, RTA, mod, nav, enerji, haberleşme, kontrol otoritesi, FDIR | SystemAssessment | sistem durumu | Yalnızca değerlendirir; değişim SYSTEM_STATE_CHANGED | `simurg/sim/supervisor.py::SystemSupervisor` | IMPLEMENTED |
<!-- END GENERATED: matrix-mode-supervision -->
