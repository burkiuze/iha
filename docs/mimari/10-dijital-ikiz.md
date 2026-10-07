# 10 — DIGITAL TWIN ARCHITECTURE

> Sivil mühendislik referans mimarisi — yazılım/güvenlik/simülasyon düzeyi.
> Uçuşa hazır donanım, kablolama, ESC/motor ayarı ya da kontrol kazancı içermez.
> Ana belge: [15 — Master System Architecture](../15-sistem-mimarisi.md).
> Diyagram ve tablolar `python -m simurg.architecture --update-all` ile üretilir.

## Koşum zinciri (korunan)

```mermaid
flowchart LR
  SC["Scenario Manager"] --> ENV["Environment"] --> SEN["Sensor Models"] --> NAV["Navigation"]
  NAV --> PROP["Controller Proposal"] --> CV["Command Validator"] --> RTA{{"RTA"}} --> CTRL["Control + Allocation"]
  CTRL --> FCC["Triplex vote"] --> ACT["Actuator Models"] --> DYN["6-DOF Dynamics"] --> ST["State"] --> REC["Recorder / Metrics"]
  FS["Fault Schedule"] -.-> SEN & ACT & NAV & FCC & PROP
  REC --> RP["Replay"]
  MC["Monte Carlo Runner"] --> SC
```

Dijital ikiz aynı güvenlik mimarisini (validator, RTA, FDIR, Vehicle Health,
mod/acil durum, sistem denetimi) simülasyonda koşturur.

## Desteklenen yazılım arıza enjeksiyonu

| Arıza | FaultKind | Örnek senaryo |
|---|---|---|
| sensor unavailable | `sensor_dropout` | `nav_source_loss` |
| navigation degraded | `sensor_bias`, `sensor_noise` | `combined_degraded` |
| motor degraded | `actuator_degraded` | `single_actuator_degradation` |
| actuator unavailable | `actuator_offline`, `actuator_stuck` | `hover_capability_loss` |
| communication lost | `link_loss` | `communication_loss` |
| energy degraded | `energy_fc_degraded`, `energy_battery_fade`, `energy_power_limit` | `energy_reserve_warning` |
| FCC lane unavailable / divergent | `fcc_lane_unavailable`, `fcc_lane_divergence` | `fcc_lane_loss`, `fcc_lane_divergence` |
| mission computer failure | `controller_fault` (`mode: stale`) | `mission_computer_failure` |

> **Simülasyon gerçek fiziksel uçuşa elverişliliğin (flightworthiness)
> kanıtı değildir.** Aero katsayıları sentetiktir, eyleyici/sensör modelleri
> basitleştirilmiştir ve şeritler kopya hesaptır (docs/14 §12).

## Diyagram

<!-- BEGIN GENERATED: view-digital-twin -->
```mermaid
flowchart LR
  classDef implemented fill:#d7f5dd,stroke:#1a7f37,color:#0b3d1a;
  classDef partial fill:#fff4c2,stroke:#9a6700,color:#3d2e00;
  classDef unvalidated fill:#ffe1c7,stroke:#bc4c00,color:#4d1f00;
  classDef planned fill:#eef0f3,stroke:#8c959f,color:#57606a,stroke-dasharray: 4 3;
  classDef gate fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a,stroke-width:3px;
  classDef ext fill:#ffffff,stroke:#8c959f,color:#57606a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  subgraph DT["DIGITAL TWIN"]
    direction TB
    subgraph DT_RUN["Koşum altyapısı"]
      DT_SCENARIO["Scenario Manager"]:::implemented
      DT_ENGINE["Simulation Engine"]:::implemented
      DT_FAULTS["Fault Schedule / Injection"]:::implemented
      DT_MC["Monte Carlo Runner"]:::implemented
    end
    subgraph DT_PLANT["Bitki modelleri"]
      DT_ENV["Environment Model"]:::implemented
      DT_PARAMS["Vehicle Parameters"]:::implemented
      DT_SENSORS["Sensor Models"]:::implemented
      DT_NAVMODEL["Navigation Model"]:::implemented
      DT_ENERGY["Energy Model"]:::implemented
      DT_ACTUATORS["Actuator Models"]:::implemented
      DT_COMMS["Communication Model"]:::partial
      DT_FCCMODEL["FCC Lane Model"]:::partial
      DT_AERO["Aerodynamic Model"]:::implemented
      DT_DYN["Vehicle Dynamics (6-DOF)"]:::implemented
    end
    subgraph DT_ANA["Analiz"]
      DT_METRICS["Metrics"]:::implemented
      DT_REPLAY["Replay"]:::implemented
    end
  end
  AV_DEP["Distributed Electric Propulsion<br/><i>AIR VEHICLE (parametrik model)</i>"]:::ext
  AV_AIRFRAME["Box-Wing Tail-Sitter Airframe<br/><i>AIR VEHICLE (parametrik model)</i>"]:::ext
  AV_PARACHUTE["Recovery Parachute<br/><i>AIR VEHICLE (parametrik model)</i>"]:::ext
  AV_LANDING["Endplate Landing Gear<br/><i>AIR VEHICLE (parametrik model)</i>"]:::ext
  CFG_MANAGER["Configuration Manager<br/><i>CONFIGURATION</i>"]:::ext
  FDR_CORE["Flight Data Recorder<br/><i>FLIGHT DATA RECORDER</i>"]:::ext
  SEN_DRIVER["Sensor Driver<br/><i>SENSOR SUITE</i>"]:::ext
  SEN_GNSS_A["GNSS A<br/><i>SENSOR SUITE</i>"]:::ext
  EN_MANAGER["Energy Manager<br/><i>POWER / ENERGY</i>"]:::ext
  CO_GROUND["Ground Link<br/><i>COMMUNICATION</i>"]:::ext
  FCC_VOTER["Lane Voter<br/><i>TRIPLEX FLIGHT COMPUTERS</i>"]:::ext
  MC_AI["Mission AI<br/><i>MISSION COMPUTER (yalnızca öneri; uçuş-kritik değil)</i>"]:::ext
  GCS_REPLAY["Replay & Log Viewer<br/><i>GROUND SEGMENT</i>"]:::ext
  AV_DEP --> DT_DYN
  AV_AIRFRAME --> DT_DYN
  AV_PARACHUTE -->|"sürükleme"| DT_DYN
  DT_DYN -->|"temas"| AV_LANDING
  CFG_MANAGER -->|"yapılandırma"| DT_PARAMS
  FDR_CORE -->|"kayıt"| DT_REPLAY
  DT_SCENARIO --> DT_ENGINE
  DT_FAULTS -.->|"arıza takvimi"| DT_ENGINE
  DT_MC -->|"tohumlar"| DT_ENGINE
  DT_PARAMS --> DT_DYN
  DT_ENV --> DT_AERO
  DT_AERO --> DT_DYN
  DT_ACTUATORS --> DT_DYN
  DT_ENGINE -->|"adım"| DT_DYN
  DT_DYN -->|"gerçek durum"| DT_SENSORS
  DT_DYN -->|"gerçek konum"| DT_NAVMODEL
  DT_SENSORS -->|"simüle ölçüm"| SEN_DRIVER
  DT_NAVMODEL --> SEN_GNSS_A
  DT_ENERGY -->|"bitki modeli"| EN_MANAGER
  DT_COMMS -->|"bağlantı durumu"| CO_GROUND
  DT_FCCMODEL -.->|"şerit arızaları"| FCC_VOTER
  DT_FAULTS -.->|"sensör arızası"| DT_SENSORS
  DT_FAULTS -.->|"eyleyici arızası"| DT_ACTUATORS
  DT_FAULTS -.->|"bağlantı arızası"| DT_COMMS
  DT_FAULTS -.->|"enerji arızası"| DT_ENERGY
  DT_FAULTS -.->|"şerit arızası"| DT_FCCMODEL
  DT_FAULTS -.->|"öneri arızası"| MC_AI
  DT_ENGINE --> DT_METRICS
  DT_REPLAY --> DT_METRICS
  DT_METRICS -->|"sonuçlar"| GCS_REPLAY
```
<!-- END GENERATED: view-digital-twin -->

## Bileşen matrisi

<!-- BEGIN GENERATED: matrix-digital-twin -->
#### DIGITAL TWIN

| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | Code Location | Implementation Status |
|---|---|---|---|---|---|---|---|
| **Scenario Manager** `DT_SCENARIO` | Scenario Manager (simülasyon; uçuşa elverişlilik kanıtı değildir) | senaryo/yapılandırma | simülasyon çıktısı | durumsuz (n/a) | Geçersiz senaryo hiç koşturulmaz | `simurg/sim/scenarios.py::SCENARIOS` | IMPLEMENTED |
| **Simulation Engine** `DT_ENGINE` | Simulation Engine (simülasyon; uçuşa elverişlilik kanıtı değildir) | senaryo/yapılandırma | simülasyon çıktısı | durumsuz (n/a) | Sayısal hata -> sim_failed + SimulationError | `simurg/sim/engine.py::SimulationEngine` | IMPLEMENTED |
| **Fault Schedule / Injection** `DT_FAULTS` | Fault Schedule / Injection (simülasyon; uçuşa elverişlilik kanıtı değildir) | senaryo/yapılandırma | simülasyon çıktısı | durumsuz (n/a) | Geçersiz arıza hedefi senaryoyu reddeder | `simurg/sim/faults.py::FaultInjector` | IMPLEMENTED |
| **Monte Carlo Runner** `DT_MC` | Monte Carlo Runner (simülasyon; uçuşa elverişlilik kanıtı değildir) | senaryo/yapılandırma | simülasyon çıktısı | durumsuz (n/a) | Tohumla yeniden üretilebilir | `simurg/sim/montecarlo.py::MonteCarloRunner` | IMPLEMENTED |
| **Environment Model** `DT_ENV` | Environment Model (simülasyon; uçuşa elverişlilik kanıtı değildir) | senaryo/yapılandırma | simülasyon çıktısı | durumsuz (n/a) | n/a | `simurg/sim/environment.py::ConstantEnvironment` | IMPLEMENTED |
| **Vehicle Parameters** `DT_PARAMS` | Vehicle Parameters (simülasyon; uçuşa elverişlilik kanıtı değildir) | senaryo/yapılandırma | simülasyon çıktısı | durumsuz (n/a) | n/a | `simurg/core/config.py::VehicleConfig` | IMPLEMENTED |
| **Sensor Models** `DT_SENSORS` | Sensor Models (simülasyon; uçuşa elverişlilik kanıtı değildir) | senaryo/yapılandırma | simülasyon çıktısı | durumsuz (n/a) | n/a | `simurg/sim/sensors.py::SensorModel` | IMPLEMENTED |
| **Navigation Model** `DT_NAVMODEL` | Navigation Model (simülasyon; uçuşa elverişlilik kanıtı değildir) | senaryo/yapılandırma | simülasyon çıktısı | durumsuz (n/a) | n/a | `simurg/sim/sensors.py::SimulatedPositionProvider` | IMPLEMENTED |
| **Energy Model** `DT_ENERGY` | Energy Model (simülasyon; uçuşa elverişlilik kanıtı değildir) | senaryo/yapılandırma | simülasyon çıktısı | durumsuz (n/a) | n/a | `simurg/power/energy_manager.py::EnergyManager` | IMPLEMENTED |
| **Actuator Models** `DT_ACTUATORS` | Actuator Models (simülasyon; uçuşa elverişlilik kanıtı değildir) | senaryo/yapılandırma | simülasyon çıktısı | durumsuz (n/a) | n/a | `simurg/sim/actuators.py::ActuatorModel` | IMPLEMENTED |
| **Communication Model** `DT_COMMS` | Communication Model (simülasyon; uçuşa elverişlilik kanıtı değildir) | senaryo/yapılandırma | simülasyon çıktısı | durumsuz (n/a) | Yalnızca var/yok | `simurg/sim/link.py::LinkModel` | PARTIAL |
| **FCC Lane Model** `DT_FCCMODEL` | FCC Lane Model (simülasyon; uçuşa elverişlilik kanıtı değildir) | senaryo/yapılandırma | simülasyon çıktısı | durumsuz (n/a) | Şeritler kopya; ortak mod hatası gösterilemez | `simurg/sim/triplex.py::TriplexFlightComputer` | PARTIAL |
| **Aerodynamic Model** `DT_AERO` | Aerodynamic Model (simülasyon; uçuşa elverişlilik kanıtı değildir) | senaryo/yapılandırma | simülasyon çıktısı | durumsuz (n/a) | Sentetik katsayılar | `simurg/aero/model.py::AnalyticAeroModel`<br/>`simurg/aero/model.py::TableAeroModel` | IMPLEMENTED |
| **Vehicle Dynamics (6-DOF)** `DT_DYN` | Vehicle Dynamics (6-DOF) (simülasyon; uçuşa elverişlilik kanıtı değildir) | senaryo/yapılandırma | simülasyon çıktısı | durumsuz (n/a) | Sonlu olmayan durum -> SimulationError | `simurg/sim/dynamics.py::RigidBodyDynamics` | IMPLEMENTED |
| **Metrics** `DT_METRICS` | Metrics (simülasyon; uçuşa elverişlilik kanıtı değildir) | senaryo/yapılandırma | simülasyon çıktısı | durumsuz (n/a) | n/a | `simurg/sim/metrics.py::compute_metrics` | IMPLEMENTED |
| **Replay** `DT_REPLAY` | Replay (simülasyon; uçuşa elverişlilik kanıtı değildir) | senaryo/yapılandırma | simülasyon çıktısı | durumsuz (n/a) | n/a | `simurg/sim/replay.py::ReplaySession` | IMPLEMENTED |
<!-- END GENERATED: matrix-digital-twin -->
