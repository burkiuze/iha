# 05 — POWER ARCHITECTURE

> Sivil mühendislik referans mimarisi — yazılım/güvenlik/simülasyon düzeyi.
> Uçuşa hazır donanım, kablolama, ESC/motor ayarı ya da kontrol kazancı içermez.
> Ana belge: [15 — Master System Architecture](../15-sistem-mimarisi.md).
> Diyagram ve tablolar `python -m simurg.architecture --update-all` ile üretilir.

## Güç akışı

```mermaid
flowchart LR
  SRC["Energy Source Models<br/>Fuel Cell · Battery · Supercap · Solar (soyut)"] --> SH["Source Health"] --> PA["Power Availability"]
  PD["Power Demand<br/>itki + aviyonik"] --> ARB["Power Arbitration"]
  PA --> ARB --> EM["Energy Manager<br/>EnergyState"] --> RE["Reserve Estimator"]
  ARB -. açık .-> BUS["Power Bus Health"]
  EM -. paylaşım .-> MM["Mission Manager"]
  RE -. paylaşım .-> CM["Contingency Manager"]
  EM -. paylaşım .-> VH["Vehicle Health"]
  RE -. paylaşım .-> SS["System Supervisor"]
```

* Kaynaklar **soyutlamadır**; fiziksel hidrojen sistemi kurulumu, yakıt
  hücresi ya da batarya donanım ayarı kapsam dışıdır.
* Enerji sağlığı: kalıcı (> 0,5 s) güç açığı → FAILED (CONTINGENCY);
  rezerv uyarısı / kaynak bozunumu → DEGRADED; sonlu olmayan kestirim → UNKNOWN.
* Emergency Energy State: rezerv yalnızca acil modlarda kullanıma açılır.
* Termal sağlık PLANNED.

## Diyagram

<!-- BEGIN GENERATED: view-power -->
```mermaid
flowchart LR
  classDef implemented fill:#d7f5dd,stroke:#1a7f37,color:#0b3d1a;
  classDef partial fill:#fff4c2,stroke:#9a6700,color:#3d2e00;
  classDef unvalidated fill:#ffe1c7,stroke:#bc4c00,color:#4d1f00;
  classDef planned fill:#eef0f3,stroke:#8c959f,color:#57606a,stroke-dasharray: 4 3;
  classDef gate fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a,stroke-width:3px;
  classDef ext fill:#ffffff,stroke:#8c959f,color:#57606a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  subgraph EN["POWER / ENERGY"]
    direction TB
    subgraph EN_SRC["Kaynak modelleri"]
      EN_FC["Fuel Cell Abstraction"]:::implemented
      EN_BATT["Battery Abstraction"]:::implemented
      EN_SC["Supercapacitor Abstraction"]:::implemented
      EN_SOLAR["Solar Abstraction"]:::partial
    end
    subgraph EN_FLOW["Güç akışı"]
      EN_AVAIL["Power Availability"]:::partial
      EN_DEMAND["Power Demand"]:::partial
      EN_ARBITRATION["Power Arbitration"]:::implemented
      EN_MANAGER["Energy Manager"]:::implemented
    end
    subgraph EN_HEALTH["Enerji sağlığı"]
      EN_SRC_HEALTH["Source Health"]:::implemented
      EN_RESERVE["Reserve Estimator"]:::implemented
      EN_BUS_HEALTH["Power Bus Health"]:::partial
      EN_THERMAL["Thermal Health"]:::planned
      EN_EMERGENCY["Emergency Energy State"]:::implemented
    end
  end
  C_VEL["Velocity Control<br/><i>FLIGHT CONTROL (yazılım soyutlaması; kazanç içermez)</i>"]:::ext
  FDIR_ENERGY["Energy FDIR<br/><i>FDIR</i>"]:::ext
  MD_FSM["Flight Mode Machine<br/><i>MODE / CONTINGENCY MANAGEMENT</i>"]:::ext
  SEN_POWER_TLM["Power Telemetry<br/><i>SENSOR SUITE</i>"]:::ext
  BUS_STATE["State Bus<br/><i>DATA BUS (mantıksal)</i>"]:::ext
  MC_MISSION_MGR["Mission Manager<br/><i>MISSION COMPUTER (yalnızca öneri; uçuş-kritik değil)</i>"]:::ext
  MD_CONTINGENCY["Contingency Manager<br/><i>MODE / CONTINGENCY MANAGEMENT</i>"]:::ext
  SUP_SYSTEM["System Supervisor<br/><i>SYSTEM SUPERVISION</i>"]:::ext
  FDR_ENERGY["Energy Recorder<br/><i>FLIGHT DATA RECORDER</i>"]:::ext
  ACT_MOTOR_GROUP["Motor Group<br/><i>ACTUATOR SYSTEM (simülasyon soyutlaması)</i>"]:::ext
  PF_ENERGY["Energy Check<br/><i>PREFLIGHT SUPERVISOR</i>"]:::ext
  DT_ENERGY["Energy Model<br/><i>DIGITAL TWIN</i>"]:::ext
  EN_AVAIL -.->|"güç sınırı"| C_VEL
  EN_MANAGER -.->|"EnergyState"| FDIR_ENERGY
  EN_RESERVE -.->|"rezerv uyarısı"| FDIR_ENERGY
  EN_BUS_HEALTH -.->|"güç açığı"| FDIR_ENERGY
  EN_FC -.-> EN_SRC_HEALTH
  EN_BATT -.-> EN_SRC_HEALTH
  EN_SC -.-> EN_SRC_HEALTH
  EN_SOLAR --> EN_AVAIL
  EN_FC --> EN_AVAIL
  EN_BATT --> EN_AVAIL
  EN_SC --> EN_AVAIL
  EN_SRC_HEALTH -.-> EN_AVAIL
  EN_DEMAND --> EN_ARBITRATION
  EN_AVAIL --> EN_ARBITRATION
  EN_ARBITRATION -->|"PowerSplit"| EN_MANAGER
  EN_MANAGER --> EN_RESERVE
  EN_ARBITRATION -.-> EN_BUS_HEALTH
  EN_THERMAL -.-> EN_SRC_HEALTH
  MD_FSM -.->|"acil mod"| EN_EMERGENCY
  EN_EMERGENCY -.->|"rezerv kilidi"| EN_ARBITRATION
  EN_MANAGER -->|"güç telemetrisi"| SEN_POWER_TLM
  EN_MANAGER -->|"EnergyState"| BUS_STATE
  EN_RESERVE -.->|"rezerv kısıtı"| MC_MISSION_MGR
  EN_RESERVE -.->|"eve dönüş/iniş enerjisi"| MD_CONTINGENCY
  EN_RESERVE -.->|"enerji uyarısı"| SUP_SYSTEM
  EN_MANAGER --> FDR_ENERGY
  ACT_MOTOR_GROUP -->|"itki -> elektrik yükü"| EN_DEMAND
  EN_MANAGER -.->|"kullanılabilir enerji"| PF_ENERGY
  DT_ENERGY -->|"bitki modeli"| EN_MANAGER
```
<!-- END GENERATED: view-power -->

## Bileşen matrisi

<!-- BEGIN GENERATED: matrix-power -->
#### POWER / ENERGY

| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | Code Location | Implementation Status |
|---|---|---|---|---|---|---|---|
| **Fuel Cell Abstraction** `EN_FC` | PEM gücü, eğim sınırı, H2 tüketimi (soyut) | hedef güç | FC gücü | NOMINAL/DEGRADED/FAILED/UNKNOWN | Bozunum -> güç ölçeği düşer Yedeklilik: hibrit kaynak. | `simurg/power/energy_manager.py::fc_efficiency` | IMPLEMENTED — Fiziksel hidrojen sistemi kurulumu kapsam dışı |
| **Battery Abstraction** `EN_BATT` | SoC, deşarj sınırı | güç | SoC | NOMINAL/DEGRADED/FAILED/UNKNOWN | Kapasite kaybı kalıcı; rezerv uyarısı Yedeklilik: hibrit kaynak. | `simurg/power/energy_manager.py::EnergyManager` | IMPLEMENTED |
| **Supercapacitor Abstraction** `EN_SC` | Tepe güç tamponu | güç | SoC | NOMINAL/DEGRADED/FAILED/UNKNOWN | Bara akım sınırında tükenir Yedeklilik: hibrit kaynak. | `simurg/power/energy_manager.py::EnergyManager` | IMPLEMENTED |
| **Solar Abstraction** `EN_SOLAR` | Güneş katkısı | güneş girdisi | güç | NOMINAL/DEGRADED/FAILED/UNKNOWN | Yok sayılır (0 W) | `simurg/power/energy_manager.py::EnergyManager` | PARTIAL — Birim testli; simülasyon motorunda 0 W |
| **Source Health** `EN_SRC_HEALTH` | Kaynak bozunum özeti | ölçekler | health 0..1 | NOMINAL/DEGRADED/FAILED/UNKNOWN | < 1 -> DEGRADED | `simurg/power/energy_manager.py::EnergyManager` | IMPLEMENTED |
| **Power Availability** `EN_AVAIL` | Kaynak başına anlık güç sınırı | SoC, ölçekler | kullanılabilir güç | durumsuz (n/a) | Talep > kullanılabilir -> karşılanamayan güç | `simurg/power/energy_manager.py::EnergyManager` | PARTIAL |
| **Power Demand** `EN_DEMAND` | İtki + aviyonik elektrik yükü | itki, hız | anlık talep | durumsuz (n/a) | n/a | `simurg/sim/propulsion.py::PropulsionModel` | PARTIAL — İleri tahmin planlanan |
| **Power Arbitration** `EN_ARBITRATION` | Frekans ayrıştırmalı kaynak paylaşımı | talep, sınırlar | PowerSplit | durumsuz (n/a) | Açık > 0,5 s -> güç alanı FAILED; itki ölçeklenir | `simurg/power/energy_manager.py::EnergyManager` | IMPLEMENTED |
| **Energy Manager** `EN_MANAGER` | Hibrit enerji yönetimi, EnergyState | talep | EnergyState | NOMINAL/DEGRADED/FAILED/UNKNOWN | Sonlu olmayan kestirim -> UNKNOWN | `simurg/power/energy_manager.py::EnergyManager` | IMPLEMENTED |
| **Reserve Estimator** `EN_RESERVE` | Eve dönüş/iniş enerjisi ve uyarı histerezisi | kullanılabilir enerji, mesafe | ReserveAssessment | bilinmeyen enerji -> uyarı | Uyarı -> görev iptali + RETURN | `simurg/power/reserve.py::ReserveMonitor` | IMPLEMENTED |
| **Power Bus Health** `EN_BUS_HEALTH` | Karşılanamayan güç, itki güç faktörü | PowerSplit | bara sağlığı | NOMINAL/DEGRADED/FAILED/UNKNOWN | Kalıcı açık -> FAILED | `simurg/sim/engine.py::SimulationEngine` | PARTIAL — Güç dengesi düzeyinde; gerilim modellenmez |
| **Thermal Health** `EN_THERMAL` | Batarya/FC sıcaklığı | güç | sıcaklık | NOMINAL/DEGRADED/FAILED/UNKNOWN | Planlanan | — | PLANNED |
| **Emergency Energy State** `EN_EMERGENCY` | Acil modlarda rezervin kullanıma açılması | mod | rezerv kilidi | durumsuz (n/a) | Rezerv yalnızca acil durumda | `simurg/power/energy_manager.py::EnergyManager` | IMPLEMENTED |
<!-- END GENERATED: matrix-power -->
