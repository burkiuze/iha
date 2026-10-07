# 06 — ACTUATOR / CONTROL ALLOCATION ARCHITECTURE

> Sivil mühendislik referans mimarisi — yazılım/güvenlik/simülasyon düzeyi.
> Uçuşa hazır donanım, kablolama, ESC/motor ayarı ya da kontrol kazancı içermez.
> Ana belge: [15 — Master System Architecture](../15-sistem-mimarisi.md).
> Diyagram ve tablolar `python -m simurg.architecture --update-all` ile üretilir.

## Zincir

```mermaid
flowchart LR
  VC["Validated Command"] ==> CD["Control Demand"] ==> AA["Available Authority"] ==> HA["Health-Aware Allocation"]
  HA ==> CL["Command Limiter"] ==> FCC["Triplex vote"] ==> CM["Actuator Command Manager"]
  CM ==> MG["Motor Group<br/>M1U…M4L"]
  CM ==> EG["Elevon Group<br/>E1U · E2U · E1L · E2L"]
  HG["Actuator Health Gate<br/>FAILED → 0"] -. dağıtım dışı .-> HA
  MG --> FB["Actuator Feedback"] --> MH["Motor Health"] -. sağlık .-> HG
  HA --> RES["Allocation Residual / Saturation"]
  MH -. kalan otorite .-> AA
```

* **FAILED eyleyici nominal dağıtıma alınmaz:** dağıtıcı FAILED sütunu 0'da
  sabitler (`test_system_of_systems.test_failed_actuator_receives_no_nominal_allocation`);
  çıkarma `actuator_excluded` olayıyla kaydedilir ve
  `ReplaySession.why_actuator_removed()` ile açıklanır.
* Geri beslemeler: actuator feedback, motor health, saturation state,
  allocation residual, remaining control authority (hover marjı).
* Eyleyiciler **simülasyon soyutlamasıdır**: gerçek motor sürme protokolü,
  ESC firmware ayarı ya da uçuşa hazır eyleyici ayarı içermez.

## Diyagram

<!-- BEGIN GENERATED: view-allocation-actuators -->
```mermaid
flowchart LR
  classDef implemented fill:#d7f5dd,stroke:#1a7f37,color:#0b3d1a;
  classDef partial fill:#fff4c2,stroke:#9a6700,color:#3d2e00;
  classDef unvalidated fill:#ffe1c7,stroke:#bc4c00,color:#4d1f00;
  classDef planned fill:#eef0f3,stroke:#8c959f,color:#57606a,stroke-dasharray: 4 3;
  classDef gate fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a,stroke-width:3px;
  classDef ext fill:#ffffff,stroke:#8c959f,color:#57606a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  subgraph ALLOC["CONTROL ALLOCATION"]
    direction TB
    AL_DEMAND["Control Demand"]:::implemented
    AL_EFFECTIVENESS["Effectiveness B(V, σ)"]:::implemented
    AL_AUTHORITY["Available Authority"]:::implemented
    AL_ALLOCATOR["Health-Aware Allocation"]:::implemented
    AL_LIMITER["Command Limiter"]:::implemented
    AL_RESIDUAL["Allocation Residual / Saturation"]:::implemented
  end
  subgraph ACT["ACTUATOR SYSTEM (simülasyon soyutlaması)"]
    direction TB
    subgraph ACT_CMD["Komut yönetimi"]
      ACT_CMD_MGR["Actuator Command Manager"]:::implemented
      ACT_HEALTH_GATE["Actuator Health Gate"]:::implemented
    end
    subgraph ACT_M["Motor Group"]
      ACT_MOTOR_GROUP["Motor Group"]:::implemented
      ACT_M1U["Motor M1U"]:::implemented
      ACT_M2U["Motor M2U"]:::implemented
      ACT_M3U["Motor M3U"]:::implemented
      ACT_M4U["Motor M4U"]:::implemented
      ACT_M1L["Motor M1L"]:::implemented
      ACT_M2L["Motor M2L"]:::implemented
      ACT_M3L["Motor M3L"]:::implemented
      ACT_M4L["Motor M4L"]:::implemented
    end
    subgraph ACT_E["Elevon Group"]
      ACT_ELEVON_GROUP["Elevon Group"]:::implemented
      ACT_E1U["Elevon E1U"]:::implemented
      ACT_E2U["Elevon E2U"]:::implemented
      ACT_E1L["Elevon E1L"]:::implemented
      ACT_E2L["Elevon E2L"]:::implemented
    end
    subgraph ACT_FB["Geri besleme"]
      ACT_FEEDBACK["Actuator Feedback"]:::implemented
      ACT_MOTOR_HEALTH["Motor Health"]:::implemented
      ACT_SATURATION["Saturation State"]:::implemented
    end
  end
  subgraph AV["AIR VEHICLE (parametrik model)"]
    direction TB
    AV_AIRFRAME["Box-Wing Tail-Sitter Airframe"]:::partial
    AV_DEP["Distributed Electric Propulsion"]:::partial
    AV_PARACHUTE["Recovery Parachute"]:::implemented
    AV_LANDING["Endplate Landing Gear"]:::implemented
  end
  C_ATT["Attitude Control<br/><i>FLIGHT CONTROL (yazılım soyutlaması; kazanç içermez)</i>"]:::ext
  C_VEL["Velocity Control<br/><i>FLIGHT CONTROL (yazılım soyutlaması; kazanç içermez)</i>"]:::ext
  FDIR_SURFACE_MON["Surface Monitor<br/><i>FDIR</i>"]:::ext
  FCC_A_OUT["Output Proposal<br/><i>TRIPLEX FLIGHT COMPUTERS</i>"]:::ext
  FCC_B_OUT["Output Proposal<br/><i>TRIPLEX FLIGHT COMPUTERS</i>"]:::ext
  FCC_C_OUT["Output Proposal (C)<br/><i>TRIPLEX FLIGHT COMPUTERS</i>"]:::ext
  FCC_VOTER["Lane Voter<br/><i>TRIPLEX FLIGHT COMPUTERS</i>"]:::ext
  SEN_RPM["Motor / ESC Telemetry<br/><i>SENSOR SUITE</i>"]:::ext
  SEN_ACT_POS["Actuator Position Feedback<br/><i>SENSOR SUITE</i>"]:::ext
  DT_DYN["Vehicle Dynamics (6-DOF)<br/><i>DIGITAL TWIN</i>"]:::ext
  MD_FSM["Flight Mode Machine<br/><i>MODE / CONTINGENCY MANAGEMENT</i>"]:::ext
  BUS_EVENT["Event Bus<br/><i>DATA BUS (mantıksal)</i>"]:::ext
  FDIR_MOTOR_MON["Motor Monitor (CUSUM)<br/><i>FDIR</i>"]:::ext
  FDIR_MOTOR["Motor FDIR<br/><i>FDIR</i>"]:::ext
  EN_DEMAND["Power Demand<br/><i>POWER / ENERGY</i>"]:::ext
  MD_CONTINGENCY["Contingency Manager<br/><i>MODE / CONTINGENCY MANAGEMENT</i>"]:::ext
  PF_CTRL["Control Authority Check<br/><i>PREFLIGHT SUPERVISOR</i>"]:::ext
  PF_ACT["Actuator Health Check<br/><i>PREFLIGHT SUPERVISOR</i>"]:::ext
  CFG_VEHICLE["Vehicle Parameters<br/><i>CONFIGURATION</i>"]:::ext
  C_ATT ==>|"moment"| AL_DEMAND
  C_VEL ==>|"itki"| AL_DEMAND
  AL_EFFECTIVENESS -->|"B(V,σ)"| AL_ALLOCATOR
  AL_EFFECTIVENESS --> AL_AUTHORITY
  AL_DEMAND ==> AL_AUTHORITY
  AL_AUTHORITY ==> AL_ALLOCATOR
  ACT_MOTOR_HEALTH -.->|"sağlık vektörü"| AL_AUTHORITY
  FDIR_SURFACE_MON -.->|"yüzey sağlığı"| ACT_HEALTH_GATE
  ACT_HEALTH_GATE -.->|"FAILED sütun = 0"| AL_ALLOCATOR
  AL_ALLOCATOR ==> AL_LIMITER
  AL_ALLOCATOR --> AL_RESIDUAL
  AL_LIMITER ==>|"şerit önerisi"| FCC_A_OUT
  AL_LIMITER ==>|"şerit önerisi"| FCC_B_OUT
  AL_LIMITER ==>|"şerit önerisi"| FCC_C_OUT
  FCC_VOTER ==>|"oylanmış komut"| ACT_CMD_MGR
  ACT_CMD_MGR ==>|"itki komutları"| ACT_MOTOR_GROUP
  ACT_CMD_MGR ==>|"sapma komutları"| ACT_ELEVON_GROUP
  ACT_MOTOR_GROUP ==> ACT_M1U
  ACT_MOTOR_GROUP ==> ACT_M2U
  ACT_MOTOR_GROUP ==> ACT_M3U
  ACT_MOTOR_GROUP ==> ACT_M4U
  ACT_MOTOR_GROUP ==> ACT_M1L
  ACT_MOTOR_GROUP ==> ACT_M2L
  ACT_MOTOR_GROUP ==> ACT_M3L
  ACT_MOTOR_GROUP ==> ACT_M4L
  ACT_ELEVON_GROUP ==> ACT_E1U
  ACT_ELEVON_GROUP ==> ACT_E2U
  ACT_ELEVON_GROUP ==> ACT_E1L
  ACT_ELEVON_GROUP ==> ACT_E2L
  ACT_MOTOR_GROUP --> ACT_FEEDBACK
  ACT_ELEVON_GROUP --> ACT_FEEDBACK
  ACT_FEEDBACK -->|"devir"| SEN_RPM
  ACT_FEEDBACK -->|"konum"| SEN_ACT_POS
  ACT_FEEDBACK --> ACT_MOTOR_HEALTH
  AL_RESIDUAL --> ACT_SATURATION
  ACT_MOTOR_HEALTH -.->|"sağlık"| ACT_HEALTH_GATE
  ACT_MOTOR_GROUP -->|"itki"| AV_DEP
  ACT_ELEVON_GROUP -->|"sapma"| AV_AIRFRAME
  AV_DEP --> DT_DYN
  AV_AIRFRAME --> DT_DYN
  AV_PARACHUTE -->|"sürükleme"| DT_DYN
  MD_FSM -.->|"PARACHUTE modu"| AV_PARACHUTE
  DT_DYN -->|"temas"| AV_LANDING
  AV_LANDING -->|"touchdown/impact"| BUS_EVENT
  FDIR_MOTOR_MON --> ACT_MOTOR_HEALTH
  AL_AUTHORITY -.->|"hover fizibilitesi"| FDIR_MOTOR
  ACT_MOTOR_GROUP -->|"itki -> elektrik yükü"| EN_DEMAND
  AL_AUTHORITY -.->|"hover fizibilitesi"| MD_CONTINGENCY
  AL_AUTHORITY -.->|"hover marjı"| PF_CTRL
  ACT_FEEDBACK -.->|"BIT"| PF_ACT
  CFG_VEHICLE --> AL_EFFECTIVENESS
```
<!-- END GENERATED: view-allocation-actuators -->

## Bileşen matrisi

<!-- BEGIN GENERATED: matrix-allocation-actuators -->
#### CONTROL ALLOCATION

| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | Code Location | Implementation Status |
|---|---|---|---|---|---|---|---|
| **Control Demand** `AL_DEMAND` | İtki + moment isteği vektörü | kontrol yasaları | v_des | durumsuz (n/a) | Sonlu olmayan istek -> SimulationError | `simurg/control/effectiveness.py::body_to_alloc` | IMPLEMENTED |
| **Effectiveness B(V, σ)** `AL_EFFECTIVENESS` | Rejime bağlı etkinlik matrisi | hız, σ, yapılandırma | ControlRegime | durumsuz (n/a) | İç motorlar seyirde katlı (B sütunu 0) | `simurg/control/effectiveness.py::ScheduledEffectiveness` | IMPLEMENTED |
| **Available Authority** `AL_AUTHORITY` | Askı marjı (itki/ağırlık) ve kalan otorite | sağlık vektörü | hover marjı | bilinmeyen eyleyici havada = çalışmıyor | Marj < eşik -> hover_feasible=False -> acil iniş kuralı | `simurg/sim/health.py::HealthSupervisor` | IMPLEMENTED |
| **Health-Aware Allocation** `AL_ALLOCATOR` | Sağlık ağırlıklı RPI dağıtımı | v_des, sağlık, rejim | eyleyici komutu, doyma, artık | durumsuz (n/a) | Doyma -> artık (allocation residual) raporlanır | `simurg/control/allocation.py::ControlAllocator` | IMPLEMENTED |
| **Command Limiter** `AL_LIMITER` | Eyleyici sınırlarına kırpma | dağıtım çıktısı | sınırlı komut | durumsuz (n/a) | Sınır dışı komut eyleyiciye gitmez | `simurg/control/allocation.py::ControlAllocator` | IMPLEMENTED |
| **Allocation Residual / Saturation** `AL_RESIDUAL` | İstenen - elde edilen; doyma oranı | dağıtım | artık, doyma | durumsuz (n/a) | Kalıcı otorite açığı -> kontrol kaybı zamanlayıcısı | `simurg/control/allocation.py::AllocationResult` | IMPLEMENTED |

#### ACTUATOR SYSTEM (simülasyon soyutlaması)

| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | Code Location | Implementation Status |
|---|---|---|---|---|---|---|---|
| **Actuator Command Manager** `ACT_CMD_MGR` | Oylanmış komutun zaman damgasıyla dağıtımı | oylanmış komut | ActuatorCommand | durumsuz (n/a) | Çıktı yoksa son oylanmış komut tutulur + kontrol kaybı bayrağı | `simurg/sim/actuators.py::ActuatorCommand` | IMPLEMENTED |
| **Actuator Health Gate** `ACT_HEALTH_GATE` | FAILED eyleyici nominal dağıtıma ALINMAZ (komut 0) | sağlık vektörü | kapılı dağıtım | durumsuz (n/a) | ACTUATOR_EXCLUDED olayı + yeni hover marjı | `simurg/control/allocation.py::ControlAllocator` | IMPLEMENTED — Simülasyonda dağıtıcı içinde (oylama öncesi) uygulanır |
| **Motor Group** `ACT_MOTOR_GROUP` | 8 motor DEP (iç 4'ü seyirde katlanır) | itki komutları | itkiler | NOMINAL/DEGRADED/FAILED/UNKNOWN | Tek motor kaybı tolere; aynı uçta iki motor -> hover yok -> süzülerek acil iniş Yedeklilik: 8 motor; herhangi tek motor kaybı askıda tolere. | `simurg/sim/actuators.py::ActuatorModel` | IMPLEMENTED |
| **Motor M1U** `ACT_M1U` | Motor + pervane (gecikme, tepki, doyma) | normalize itki | itki, devir | NOMINAL/DEGRADED/STUCK/OFFLINE | Verim kaybı -> DEGRADED; devir yok -> FAILED -> dağıtım dışı Yedeklilik: motor grubu. | `simurg/sim/actuators.py::ActuatorModel` | IMPLEMENTED |
| **Motor M2U** `ACT_M2U` | Motor + pervane (gecikme, tepki, doyma) | normalize itki | itki, devir | NOMINAL/DEGRADED/STUCK/OFFLINE | Verim kaybı -> DEGRADED; devir yok -> FAILED -> dağıtım dışı Yedeklilik: motor grubu. | `simurg/sim/actuators.py::ActuatorModel` | IMPLEMENTED |
| **Motor M3U** `ACT_M3U` | Motor + pervane (gecikme, tepki, doyma) | normalize itki | itki, devir | NOMINAL/DEGRADED/STUCK/OFFLINE | Verim kaybı -> DEGRADED; devir yok -> FAILED -> dağıtım dışı Yedeklilik: motor grubu. | `simurg/sim/actuators.py::ActuatorModel` | IMPLEMENTED |
| **Motor M4U** `ACT_M4U` | Motor + pervane (gecikme, tepki, doyma) | normalize itki | itki, devir | NOMINAL/DEGRADED/STUCK/OFFLINE | Verim kaybı -> DEGRADED; devir yok -> FAILED -> dağıtım dışı Yedeklilik: motor grubu. | `simurg/sim/actuators.py::ActuatorModel` | IMPLEMENTED |
| **Motor M1L** `ACT_M1L` | Motor + pervane (gecikme, tepki, doyma) | normalize itki | itki, devir | NOMINAL/DEGRADED/STUCK/OFFLINE | Verim kaybı -> DEGRADED; devir yok -> FAILED -> dağıtım dışı Yedeklilik: motor grubu. | `simurg/sim/actuators.py::ActuatorModel` | IMPLEMENTED |
| **Motor M2L** `ACT_M2L` | Motor + pervane (gecikme, tepki, doyma) | normalize itki | itki, devir | NOMINAL/DEGRADED/STUCK/OFFLINE | Verim kaybı -> DEGRADED; devir yok -> FAILED -> dağıtım dışı Yedeklilik: motor grubu. | `simurg/sim/actuators.py::ActuatorModel` | IMPLEMENTED |
| **Motor M3L** `ACT_M3L` | Motor + pervane (gecikme, tepki, doyma) | normalize itki | itki, devir | NOMINAL/DEGRADED/STUCK/OFFLINE | Verim kaybı -> DEGRADED; devir yok -> FAILED -> dağıtım dışı Yedeklilik: motor grubu. | `simurg/sim/actuators.py::ActuatorModel` | IMPLEMENTED |
| **Motor M4L** `ACT_M4L` | Motor + pervane (gecikme, tepki, doyma) | normalize itki | itki, devir | NOMINAL/DEGRADED/STUCK/OFFLINE | Verim kaybı -> DEGRADED; devir yok -> FAILED -> dağıtım dışı Yedeklilik: motor grubu. | `simurg/sim/actuators.py::ActuatorModel` | IMPLEMENTED |
| **Elevon Group** `ACT_ELEVON_GROUP` | 4 elevon (kutu kanat) | sapma komutları | sapmalar | NOMINAL/DEGRADED/FAILED/UNKNOWN | Tek yüzey kaybı -> DEGRADED; tümü -> FAILED (itki diferansiyeli) Yedeklilik: 4 yüzey. | `simurg/sim/actuators.py::ActuatorModel` | IMPLEMENTED |
| **Elevon E1U** `ACT_E1U` | Kontrol yüzeyi (soyutlama) | normalize sapma | sapma, konum | NOMINAL/DEGRADED/STUCK/OFFLINE | Takılı/devre dışı -> konum artığı -> FAILED -> dağıtım dışı Yedeklilik: elevon grubu. | `simurg/sim/actuators.py::ActuatorModel` | IMPLEMENTED |
| **Elevon E2U** `ACT_E2U` | Kontrol yüzeyi (soyutlama) | normalize sapma | sapma, konum | NOMINAL/DEGRADED/STUCK/OFFLINE | Takılı/devre dışı -> konum artığı -> FAILED -> dağıtım dışı Yedeklilik: elevon grubu. | `simurg/sim/actuators.py::ActuatorModel` | IMPLEMENTED |
| **Elevon E1L** `ACT_E1L` | Kontrol yüzeyi (soyutlama) | normalize sapma | sapma, konum | NOMINAL/DEGRADED/STUCK/OFFLINE | Takılı/devre dışı -> konum artığı -> FAILED -> dağıtım dışı Yedeklilik: elevon grubu. | `simurg/sim/actuators.py::ActuatorModel` | IMPLEMENTED |
| **Elevon E2L** `ACT_E2L` | Kontrol yüzeyi (soyutlama) | normalize sapma | sapma, konum | NOMINAL/DEGRADED/STUCK/OFFLINE | Takılı/devre dışı -> konum artığı -> FAILED -> dağıtım dışı Yedeklilik: elevon grubu. | `simurg/sim/actuators.py::ActuatorModel` | IMPLEMENTED |
| **Actuator Feedback** `ACT_FEEDBACK` | Çıkış, beklenen çıkış, konum | eyleyici modeli | ActuatorState | durumsuz (n/a) | Geri besleme yok -> ilgili FDIR UNKNOWN | `simurg/sim/actuators.py::ActuatorState` | IMPLEMENTED |
| **Motor Health** `ACT_MOTOR_HEALTH` | Motor başına sağlık + verim kestirimi | devir artığı | sağlık vektörü (motor) | NOMINAL/DEGRADED/FAILED/UNKNOWN | Gözlenmemiş motor havada UNKNOWN | `simurg/fdir/monitor.py::MotorHealthMonitor` | IMPLEMENTED |
| **Saturation State** `ACT_SATURATION` | Doyma oranı | dağıtım | saturation_fraction | durumsuz (n/a) | Kalıcı doyma geçiş iptali ölçütüne girer | `simurg/sim/vehicle_control.py::VehicleController` | IMPLEMENTED |

#### AIR VEHICLE (parametrik model)

| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | Code Location | Implementation Status |
|---|---|---|---|---|---|---|---|
| **Box-Wing Tail-Sitter Airframe** `AV_AIRFRAME` | Kutu kanat, kuyruksuz, uç levhaları | - | kütle/atalet/geometri | durumsuz (n/a) | Yapısal arıza modellenmez | `simurg/core/config.py::VehicleConfig` | PARTIAL — Parametrik; yapısal model yok |
| **Distributed Electric Propulsion** `AV_DEP` | 8 motor yerleşimi ve itki ekseni | - | motor geometrisi | durumsuz (n/a) | Motor arızası eyleyici modelinde Yedeklilik: 8 motor. | `simurg/core/config.py::VehicleConfig` | PARTIAL |
| **Recovery Parachute** `AV_PARACHUTE` | Son çare kurtarma (sürükleme modeli) | PARACHUTE modu | sürükleme kuvveti | durumsuz (n/a) | Açılma gecikmesi 1 s; açılmama modellenmez | `simurg/sim/engine.py::SimulationEngine` | IMPLEMENTED |
| **Endplate Landing Gear** `AV_LANDING` | Uç levhaları ile dikey iniş / temas sınıflandırma | temas hızı, tutum | Touchdown | durumsuz (n/a) | Sert temas -> IMPACT olayı | `simurg/sim/ground.py::classify_touchdown` | IMPLEMENTED |
<!-- END GENERATED: matrix-allocation-actuators -->
