# 09 — TIME / DATA BUS / CONFIGURATION / FLIGHT DATA RECORDER

> Sivil mühendislik referans mimarisi — yazılım/güvenlik/simülasyon düzeyi.
> Uçuşa hazır donanım, kablolama, ESC/motor ayarı ya da kontrol kazancı içermez.
> Ana belge: [15 — Master System Architecture](../15-sistem-mimarisi.md).
> Diyagram ve tablolar `python -m simurg.architecture --update-all` ile üretilir.

* **Zaman:** sabit adımlı monoton simülasyon saati ve 14 adımlı tick sırası
  (`TICK_ORDER`); sensör zaman damgası + tazelik denetimi. Saat tutarlılığı,
  zamanlayıcı sağlığı ve şerit zamanlama izleme PLANNED.
* **Mantıksal veri yolları:** State, Measurement, Health, Command, Event,
  Telemetry. Event Bus senkron ve sıra numaralıdır (determinizm).
* **Yapılandırma:** güvenlik-kritik parametreler değişmezdir (frozen
  dataclass, testli); uçuş sırasında kontrolsüz değişiklik yapılamaz.
* **Flight Data Recorder:** kayıpsız olay kaydı + periyodik görüntü,
  sürümlü şema (`simurg.sim-log` v1). Mantıksal kanallar: state, health,
  mode, fdir, rta, navigation, energy, command, fcc, sensors, system, faults
  (`RECORDER_CHANNELS`; her olay türü bir kanala eşlidir — testli).

## Açıklanabilirlik soruları

| Soru | API |
|---|---|
| Why did RTA intervene? | `ReplaySession.why_rta_intervened()` |
| Why was Lane B isolated? | `ReplaySession.why_lane_isolated("B")` |
| Why did navigation become degraded? | `ReplaySession.why_nav_degraded()` |
| Why did mode change to RETURN? | `ReplaySession.why_mode("RETURN")` |
| Why was an actuator removed from allocation? | `ReplaySession.why_actuator_removed("M1U")` |
| Why was a command rejected? | `ReplaySession.why_command_rejected()` |

## Diyagram

<!-- BEGIN GENERATED: view-infrastructure -->
```mermaid
flowchart LR
  classDef implemented fill:#d7f5dd,stroke:#1a7f37,color:#0b3d1a;
  classDef partial fill:#fff4c2,stroke:#9a6700,color:#3d2e00;
  classDef unvalidated fill:#ffe1c7,stroke:#bc4c00,color:#4d1f00;
  classDef planned fill:#eef0f3,stroke:#8c959f,color:#57606a,stroke-dasharray: 4 3;
  classDef gate fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a,stroke-width:3px;
  classDef ext fill:#ffffff,stroke:#8c959f,color:#57606a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  subgraph TIME["TIME / SYNCHRONIZATION"]
    direction TB
    TM_CLOCK["System Clock"]:::implemented
    TM_SENSOR_TS["Sensor Timestamp Manager"]:::implemented
    TM_CONSISTENCY["Clock Consistency"]:::planned
    TM_SCHEDULER["Scheduler"]:::implemented
    TM_SCHED_HEALTH["Scheduler Health"]:::planned
    TM_TIMING_MON["Timing Monitor"]:::planned
  end
  subgraph BUS["DATA BUS (mantıksal)"]
    direction TB
    BUS_STATE["State Bus"]:::partial
    BUS_MEAS["Measurement Bus"]:::implemented
    BUS_HEALTH["Health Bus"]:::partial
    BUS_COMMAND["Command Bus"]:::partial
    BUS_EVENT["Event Bus"]:::implemented
    BUS_TLM["Telemetry Bus"]:::partial
  end
  subgraph CFG["CONFIGURATION"]
    direction TB
    CFG_MANAGER["Configuration Manager"]:::partial
    CFG_SAFETY["Safety Configuration"]:::implemented
    CFG_VEHICLE["Vehicle Parameters"]:::implemented
  end
  subgraph FDR["FLIGHT DATA RECORDER"]
    direction TB
    FDR_CORE["Flight Data Recorder"]:::implemented
    FDR_STATE["State Recorder"]:::implemented
    FDR_HEALTH["Health Recorder"]:::implemented
    FDR_MODE["Mode Recorder"]:::implemented
    FDR_FDIR["FDIR Recorder"]:::implemented
    FDR_RTA["RTA Recorder"]:::implemented
    FDR_NAV["Navigation Recorder"]:::implemented
    FDR_ENERGY["Energy Recorder"]:::implemented
    FDR_CMD["Command Recorder"]:::implemented
    FDR_FCC["FCC Lane Recorder"]:::implemented
    FDR_EXPLAIN["Decision Explainer"]:::implemented
  end
  CO_TLM_ROUTER["Telemetry Router<br/><i>COMMUNICATION</i>"]:::ext
  SEN_TIMESTAMP["Timestamp<br/><i>SENSOR SUITE</i>"]:::ext
  SEN_MEAS_BUS["Measurement Bus<br/><i>SENSOR SUITE</i>"]:::ext
  NAV_SRC_MGR["Navigation Source Manager<br/><i>NAVIGATION</i>"]:::ext
  NAV_SUPERVISOR["Navigation Supervisor<br/><i>NAVIGATION</i>"]:::ext
  EST_VEHICLE_STATE["VehicleState<br/><i>STATE ESTIMATION</i>"]:::ext
  MC_MISSION_MGR["Mission Manager<br/><i>MISSION COMPUTER (yalnızca öneri; uçuş-kritik değil)</i>"]:::ext
  G_MISSION["Mission Guidance<br/><i>GUIDANCE</i>"]:::ext
  CV_FRESHNESS["Timestamp / Freshness<br/><i>COMMAND VALIDATION</i>"]:::ext
  CV_VALIDATOR["Command Validator<br/><i>COMMAND VALIDATION</i>"]:::ext
  RTA_IN_STATE["Vehicle State Input<br/><i>RUNTIME ASSURANCE (Simplex)</i>"]:::ext
  C_SAFETY["Safety Controller<br/><i>FLIGHT CONTROL (yazılım soyutlaması; kazanç içermez)</i>"]:::ext
  RTA_RECORDER["Intervention Recorder<br/><i>RUNTIME ASSURANCE (Simplex)</i>"]:::ext
  RTA_HEALTH["RTA Runtime Health<br/><i>RUNTIME ASSURANCE (Simplex)</i>"]:::ext
  RTA_ENVELOPE["Safety Envelope<br/><i>RUNTIME ASSURANCE (Simplex)</i>"]:::ext
  RTA_SELECTOR["Command Selector<br/><i>RUNTIME ASSURANCE (Simplex)</i>"]:::ext
  C_MODE_SEL["Control Law Selector<br/><i>FLIGHT CONTROL (yazılım soyutlaması; kazanç içermez)</i>"]:::ext
  FCC_A_INPUT["Input Manager<br/><i>TRIPLEX FLIGHT COMPUTERS</i>"]:::ext
  FCC_B_INPUT["Input Manager<br/><i>TRIPLEX FLIGHT COMPUTERS</i>"]:::ext
  FCC_C_TIMING["Timing Monitor<br/><i>TRIPLEX FLIGHT COMPUTERS</i>"]:::ext
  AV_LANDING["Endplate Landing Gear<br/><i>AIR VEHICLE (parametrik model)</i>"]:::ext
  VH_LEVEL["Health Level Classifier<br/><i>VEHICLE HEALTH</i>"]:::ext
  MD_CONTINGENCY["Contingency Manager<br/><i>MODE / CONTINGENCY MANAGEMENT</i>"]:::ext
  SUP_SYSTEM["System Supervisor<br/><i>SYSTEM SUPERVISION</i>"]:::ext
  EN_MANAGER["Energy Manager<br/><i>POWER / ENERGY</i>"]:::ext
  MD_FSM["Flight Mode Machine<br/><i>MODE / CONTINGENCY MANAGEMENT</i>"]:::ext
  PF_CONFIG["Configuration Check<br/><i>PREFLIGHT SUPERVISOR</i>"]:::ext
  PF_REC["Recorder Check<br/><i>PREFLIGHT SUPERVISOR</i>"]:::ext
  EST_ESTIMATOR["State Estimator<br/><i>STATE ESTIMATION</i>"]:::ext
  AL_EFFECTIVENESS["Effectiveness B(V, σ)<br/><i>CONTROL ALLOCATION</i>"]:::ext
  DT_PARAMS["Vehicle Parameters<br/><i>DIGITAL TWIN</i>"]:::ext
  FCC_ISOLATION["Lane Isolation Manager<br/><i>TRIPLEX FLIGHT COMPUTERS</i>"]:::ext
  FDIR_SUP["FDIR Supervisor<br/><i>FDIR</i>"]:::ext
  GCS_REPLAY["Replay & Log Viewer<br/><i>GROUND SEGMENT</i>"]:::ext
  DT_REPLAY["Replay<br/><i>DIGITAL TWIN</i>"]:::ext
  BUS_TLM --> CO_TLM_ROUTER
  TM_SENSOR_TS -.->|"zaman"| SEN_TIMESTAMP
  SEN_MEAS_BUS --> BUS_MEAS
  BUS_MEAS -->|"konum ölçümleri"| NAV_SRC_MGR
  NAV_SUPERVISOR -->|"nav olayları"| BUS_EVENT
  EST_VEHICLE_STATE -->|"VehicleState"| BUS_STATE
  BUS_STATE -->|"durum"| MC_MISSION_MGR
  BUS_STATE -->|"durum"| G_MISSION
  TM_CLOCK -.->|"şimdi"| CV_FRESHNESS
  CV_VALIDATOR -->|"command_rejected/accepted"| FDR_CMD
  BUS_STATE --> RTA_IN_STATE
  BUS_STATE -->|"durum"| C_SAFETY
  RTA_RECORDER --> FDR_RTA
  RTA_HEALTH -.->|"RTA sağlığı"| BUS_HEALTH
  CFG_SAFETY -->|"zarflar"| RTA_ENVELOPE
  RTA_SELECTOR ==>|"ValidatedCommand"| BUS_COMMAND
  BUS_COMMAND ==>|"ValidatedCommand"| C_MODE_SEL
  BUS_STATE --> FCC_A_INPUT
  BUS_STATE --> FCC_B_INPUT
  TM_TIMING_MON -.-> FCC_C_TIMING
  AV_LANDING -->|"touchdown/impact"| BUS_EVENT
  VH_LEVEL -.->|"VehicleHealth"| BUS_HEALTH
  BUS_HEALTH -.->|"araç sağlığı"| MD_CONTINGENCY
  BUS_HEALTH -.->|"araç sağlığı"| SUP_SYSTEM
  BUS_HEALTH --> FDR_HEALTH
  EN_MANAGER -->|"EnergyState"| BUS_STATE
  EN_MANAGER --> FDR_ENERGY
  MD_FSM -->|"aktif mod"| BUS_STATE
  MD_FSM --> FDR_MODE
  CFG_MANAGER -.-> PF_CONFIG
  FDR_CORE -.->|"kayıt alınıyor"| PF_REC
  SUP_SYSTEM -->|"system_state_changed"| BUS_EVENT
  SUP_SYSTEM -->|"sistem durumu"| BUS_TLM
  TM_CLOCK --> TM_SENSOR_TS
  TM_CLOCK --> TM_SCHEDULER
  TM_SENSOR_TS -.-> TM_CONSISTENCY
  TM_CONSISTENCY -.->|"saat kayması"| TM_TIMING_MON
  TM_SCHEDULER -.-> TM_SCHED_HEALTH
  TM_SCHED_HEALTH -.-> TM_TIMING_MON
  TM_TIMING_MON -.->|"füzyon epoku"| EST_ESTIMATOR
  CFG_SAFETY --> CFG_MANAGER
  CFG_VEHICLE --> CFG_MANAGER
  CFG_VEHICLE --> AL_EFFECTIVENESS
  CFG_SAFETY -->|"eşikler"| MD_CONTINGENCY
  CFG_MANAGER -->|"yapılandırma"| DT_PARAMS
  BUS_EVENT --> FDR_CORE
  BUS_STATE --> FDR_STATE
  FCC_ISOLATION -->|"şerit olayları"| FDR_FCC
  FDIR_SUP --> FDR_FDIR
  NAV_SUPERVISOR --> FDR_NAV
  FDR_STATE --> FDR_CORE
  FDR_HEALTH --> FDR_CORE
  FDR_MODE --> FDR_CORE
  FDR_FDIR --> FDR_CORE
  FDR_RTA --> FDR_CORE
  FDR_NAV --> FDR_CORE
  FDR_ENERGY --> FDR_CORE
  FDR_CMD --> FDR_CORE
  FDR_FCC --> FDR_CORE
  FDR_CORE --> FDR_EXPLAIN
  FDR_EXPLAIN --> GCS_REPLAY
  FDR_CORE -->|"kayıt"| DT_REPLAY
```
<!-- END GENERATED: view-infrastructure -->

## Bileşen matrisi

<!-- BEGIN GENERATED: matrix-infrastructure -->
#### TIME / SYNCHRONIZATION

| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | Code Location | Implementation Status |
|---|---|---|---|---|---|---|---|
| **System Clock** `TM_CLOCK` | Monoton simülasyon zamanı (sabit adım) | - | t | durumsuz (n/a) | Geri giden zaman yok (testli) | `simurg/sim/engine.py::SimulationEngine` | IMPLEMENTED |
| **Sensor Timestamp Manager** `TM_SENSOR_TS` | Ölçümlere zaman damgası + tazelik | ölçümler | zaman damgalı ölçümler | durumsuz (n/a) | Gelecek/bayat damga -> STALE | `simurg/core/types.py::SensorMeasurement`<br/>`simurg/sensing/pipeline.py::SensorChannel` | IMPLEMENTED |
| **Clock Consistency** `TM_CONSISTENCY` | Şerit/sensör saat tutarlılığı | zaman damgaları | saat kayması | NOMINAL/DEGRADED/FAILED/UNKNOWN | Planlanan | — | PLANNED |
| **Scheduler** `TM_SCHEDULER` | Sabit 14 adımlı tick sırası | - | TICK_ORDER | durumsuz (n/a) | Sıra sabit ve testli | `simurg/sim/engine.py::TICK_ORDER` | IMPLEMENTED |
| **Scheduler Health** `TM_SCHED_HEALTH` | Çevrim süresi/son tarih izleme | çizelge | zamanlama ihlali | NOMINAL/DEGRADED/FAILED/UNKNOWN | Planlanan (simülasyon gerçek zamanlı değil) | — | PLANNED |
| **Timing Monitor** `TM_TIMING_MON` | Şerit ve füzyon zamanlama izleme | zaman damgaları | zamanlama sağlığı | NOMINAL/DEGRADED/FAILED/UNKNOWN | Planlanan | — | PLANNED |

#### DATA BUS (mantıksal)

| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | Code Location | Implementation Status |
|---|---|---|---|---|---|---|---|
| **State Bus** `BUS_STATE` | VehicleState / NavigationSolution dağıtımı | yayıncılar | aboneler | durumsuz (n/a) | n/a | `simurg/core/types.py::VehicleState` | PARTIAL — Mantıksal kanal; süreç içi nesne geçişi |
| **Measurement Bus** `BUS_MEAS` | Doğrulanmış ölçümler | yayıncılar | aboneler | durumsuz (n/a) | n/a | `simurg/sensing/pipeline.py::MeasurementBus` | IMPLEMENTED |
| **Health Bus** `BUS_HEALTH` | FdirReport / VehicleHealth | yayıncılar | aboneler | durumsuz (n/a) | n/a | `simurg/fdir/vehicle_health.py::VehicleHealth` | PARTIAL — Mantıksal kanal; süreç içi nesne geçişi |
| **Command Bus** `BUS_COMMAND` | ValidatedCommand -> kontrol | yayıncılar | aboneler | durumsuz (n/a) | n/a | `simurg/sim/vehicle_control.py::ControlInputs` | PARTIAL — Mantıksal kanal; süreç içi nesne geçişi |
| **Event Bus** `BUS_EVENT` | Senkron, sıralı olay yayını | yayıncılar | aboneler | durumsuz (n/a) | Senkron: abone hatası yutulmaz, yukarı fırlatılır | `simurg/core/events.py::EventBus` | IMPLEMENTED |
| **Telemetry Bus** `BUS_TLM` | Telemetri ve özet durum | yayıncılar | aboneler | durumsuz (n/a) | n/a | `simurg/sim/recorder.py::SimulationRecorder` | PARTIAL — Mantıksal kanal; süreç içi nesne geçişi |

#### CONFIGURATION

| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | Code Location | Implementation Status |
|---|---|---|---|---|---|---|---|
| **Configuration Manager** `CFG_MANAGER` | Değişmez (frozen) yapılandırmaların sağlanması | senaryo | yapılandırmalar | geçersiz -> ConfigurationError | Uçuşta güvenlik parametresi değiştirilemez (frozen, testli) | `simurg/core/config.py::VehicleConfig` | PARTIAL — Dağıtık dataclass'lar |
| **Safety Configuration** `CFG_SAFETY` | Güvenlik eşikleri | - | SafetyConfig | durumsuz (n/a) | Tutarsızlık -> uçuş öncesi RTA kontrolü | `simurg/core/config.py::SafetyConfig` | IMPLEMENTED |
| **Vehicle Parameters** `CFG_VEHICLE` | Kütle, atalet, eyleyiciler | - | VehicleConfig | durumsuz (n/a) | Geçersiz -> ConfigurationError | `simurg/core/config.py::VehicleConfig` | IMPLEMENTED |

#### FLIGHT DATA RECORDER

| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | Code Location | Implementation Status |
|---|---|---|---|---|---|---|---|
| **Flight Data Recorder** `FDR_CORE` | Kayıpsız olay + periyodik görüntü; sürümlü şema | olay yolu, durum | simurg.sim-log v1 | durumsuz (n/a) | Bilinmeyen şema reddedilir; uçuş öncesi kayıt kontrolü | `simurg/sim/recorder.py::SimulationRecorder` | IMPLEMENTED |
| **State Recorder** `FDR_STATE` | Mantıksal kayıt kanalı: state | kayıt | kanal geçmişi | durumsuz (n/a) | Kanal tek kaydın görünümüdür (sıra korunur) | `simurg/sim/recorder.py::RECORDER_CHANNELS` | IMPLEMENTED |
| **Health Recorder** `FDR_HEALTH` | Mantıksal kayıt kanalı: health | kayıt | kanal geçmişi | durumsuz (n/a) | Kanal tek kaydın görünümüdür (sıra korunur) | `simurg/sim/recorder.py::RECORDER_CHANNELS` | IMPLEMENTED |
| **Mode Recorder** `FDR_MODE` | Mantıksal kayıt kanalı: mode | kayıt | kanal geçmişi | durumsuz (n/a) | Kanal tek kaydın görünümüdür (sıra korunur) | `simurg/sim/recorder.py::RECORDER_CHANNELS` | IMPLEMENTED |
| **FDIR Recorder** `FDR_FDIR` | Mantıksal kayıt kanalı: fdir | kayıt | kanal geçmişi | durumsuz (n/a) | Kanal tek kaydın görünümüdür (sıra korunur) | `simurg/sim/recorder.py::RECORDER_CHANNELS` | IMPLEMENTED |
| **RTA Recorder** `FDR_RTA` | Mantıksal kayıt kanalı: rta | kayıt | kanal geçmişi | durumsuz (n/a) | Kanal tek kaydın görünümüdür (sıra korunur) | `simurg/sim/recorder.py::RECORDER_CHANNELS` | IMPLEMENTED |
| **Navigation Recorder** `FDR_NAV` | Mantıksal kayıt kanalı: navigation | kayıt | kanal geçmişi | durumsuz (n/a) | Kanal tek kaydın görünümüdür (sıra korunur) | `simurg/sim/recorder.py::RECORDER_CHANNELS` | IMPLEMENTED |
| **Energy Recorder** `FDR_ENERGY` | Mantıksal kayıt kanalı: energy | kayıt | kanal geçmişi | durumsuz (n/a) | Kanal tek kaydın görünümüdür (sıra korunur) | `simurg/sim/recorder.py::RECORDER_CHANNELS` | IMPLEMENTED |
| **Command Recorder** `FDR_CMD` | Mantıksal kayıt kanalı: command | kayıt | kanal geçmişi | durumsuz (n/a) | Kanal tek kaydın görünümüdür (sıra korunur) | `simurg/sim/recorder.py::RECORDER_CHANNELS` | IMPLEMENTED |
| **FCC Lane Recorder** `FDR_FCC` | Mantıksal kayıt kanalı: fcc | kayıt | kanal geçmişi | durumsuz (n/a) | Kanal tek kaydın görünümüdür (sıra korunur) | `simurg/sim/recorder.py::RECORDER_CHANNELS` | IMPLEMENTED |
| **Decision Explainer** `FDR_EXPLAIN` | Neden RTA? neden şerit B? neden RETURN? neden dağıtım dışı? | kayıt | why_* yanıtları | durumsuz (n/a) | Gerekçesiz güvenlik olayı test tarafından reddedilir | `simurg/sim/replay.py::ReplaySession` | IMPLEMENTED |
<!-- END GENERATED: matrix-infrastructure -->
