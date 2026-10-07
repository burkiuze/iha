# 04 — FDIR + VEHICLE HEALTH ARCHITECTURE

> Sivil mühendislik referans mimarisi — yazılım/güvenlik/simülasyon düzeyi.
> Uçuşa hazır donanım, kablolama, ESC/motor ayarı ya da kontrol kazancı içermez.
> Ana belge: [15 — Master System Architecture](../15-sistem-mimarisi.md).
> Diyagram ve tablolar `python -m simurg.architecture --update-all` ile üretilir.

## FDIR omurgası

FDIR Supervisor altındaki sekiz alan FDIR'i (`simurg/fdir/reports.py`) aynı
standart raporu üretir:

| Alan | fault_detected | fault_isolated | fault_class | confidence | health_state | recommended_degradation |
|---|---|---|---|---|---|---|
| Sensor | kanal geçersiz/bayat | kanallar | sensor_loss / sensor_degradation | 0..1 | N/D/F/U | geri dönüş kaynağı |
| Navigation | kaynak kaybı / bütünlük | kaynaklar | nav_source_loss / nav_integrity_loss | güven | N/D/F/U | loiter_hold |
| FCC | şerit sapması / kaybı | şeritler | lane_divergence / lane_loss | 0..1 | N/D/F/U | ikili mod / acil iniş / paraşüt |
| Motor | devir artığı | motorlar | motor_degradation / motor_loss | 0..1 | N/D/F/U | dağıtımdan çıkar |
| Actuator | konum artığı | yüzeyler | actuator_loss | 0..1 | N/D/F | dağıtımdan çıkar |
| Energy | açık / rezerv / bozunum | bara, rezerv | power_shortfall / energy_degradation | 0..1 | N/D/F/U | eve dönüş |
| Communication | C2 yok | link:c2 | link_loss | 1 | N/F | bağlantı kaybı zamanlayıcısı |
| Mission Computer | geçersiz öneri | görev bilgisayarı | proposal_invalid | 0..1 | N/D/F/U | güvenlik kontrolcüsü |

## Vehicle Health Manager

```mermaid
flowchart LR
  R["8 FdirReport + kontrol otoritesi"] --> M["Vehicle Health Manager"] --> L{"seviye"}
  L -->|"kontrol kaybı / askı yedekliliği yok / şerit yok"| CR["CRITICAL"]
  L -->|"diğer FAILED alan"| CO["CONTINGENCY"]
  L -->|"herhangi bir UNKNOWN"| UN["UNKNOWN"]
  L -->|"herhangi bir DEGRADED"| DE["DEGRADED"]
  L -->|"hepsi nominal"| NO["NOMINAL"]
```

Önem sırası: CRITICAL > CONTINGENCY > UNKNOWN > DEGRADED > NOMINAL. Çıktı
`VehicleHealth(level, reasons[], domains, fdir_reports)`; değişimler
`vehicle_health_changed` olayıyla kaydedilir. **UNKNOWN hiçbir zaman NOMINAL
değildir** (`test_system_supervision.test_unknown_is_never_nominal`).

## Diyagram

<!-- BEGIN GENERATED: view-fdir-health -->
```mermaid
flowchart LR
  classDef implemented fill:#d7f5dd,stroke:#1a7f37,color:#0b3d1a;
  classDef partial fill:#fff4c2,stroke:#9a6700,color:#3d2e00;
  classDef unvalidated fill:#ffe1c7,stroke:#bc4c00,color:#4d1f00;
  classDef planned fill:#eef0f3,stroke:#8c959f,color:#57606a,stroke-dasharray: 4 3;
  classDef gate fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a,stroke-width:3px;
  classDef ext fill:#ffffff,stroke:#8c959f,color:#57606a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  subgraph FDIR["FDIR"]
    direction TB
    FDIR_SUP["FDIR Supervisor"]:::implemented
    FDIR_SENSOR["Sensor FDIR"]:::implemented
    FDIR_NAV["Navigation FDIR"]:::implemented
    FDIR_FCC["FCC FDIR"]:::implemented
    FDIR_MOTOR["Motor FDIR"]:::implemented
    FDIR_ACTUATOR["Actuator FDIR"]:::implemented
    FDIR_ENERGY["Energy FDIR"]:::implemented
    FDIR_COMM["Communication FDIR"]:::implemented
    FDIR_MC["Mission Computer FDIR"]:::implemented
    FDIR_MOTOR_MON["Motor Monitor (CUSUM)"]:::implemented
    FDIR_SURFACE_MON["Surface Monitor"]:::partial
    FDIR_REPORT["FDIR Report Format"]:::implemented
  end
  subgraph VH["VEHICLE HEALTH"]
    direction TB
    VH_MANAGER["Vehicle Health Manager"]:::implemented
    VH_LEVEL["Health Level Classifier"]:::implemented
    VH_CONTROL_AUTH["Control Authority Domain"]:::implemented
    VH_NOT_MODELED["Not-Modeled Register"]:::implemented
  end
  SEN_HEALTH["Sensor Health<br/><i>SENSOR SUITE</i>"]:::ext
  NAV_HEALTH["NavigationHealth<br/><i>NAVIGATION</i>"]:::ext
  MC_HEALTH["Mission Health<br/><i>MISSION COMPUTER (yalnızca öneri; uçuş-kritik değil)</i>"]:::ext
  ACT_HEALTH_GATE["Actuator Health Gate<br/><i>ACTUATOR SYSTEM (simülasyon soyutlaması)</i>"]:::ext
  FCC_ISOLATION["Lane Isolation Manager<br/><i>TRIPLEX FLIGHT COMPUTERS</i>"]:::ext
  SEN_RPM["Motor / ESC Telemetry<br/><i>SENSOR SUITE</i>"]:::ext
  ACT_MOTOR_HEALTH["Motor Health<br/><i>ACTUATOR SYSTEM (simülasyon soyutlaması)</i>"]:::ext
  SEN_ACT_POS["Actuator Position Feedback<br/><i>SENSOR SUITE</i>"]:::ext
  AL_AUTHORITY["Available Authority<br/><i>CONTROL ALLOCATION</i>"]:::ext
  EN_MANAGER["Energy Manager<br/><i>POWER / ENERGY</i>"]:::ext
  EN_RESERVE["Reserve Estimator<br/><i>POWER / ENERGY</i>"]:::ext
  EN_BUS_HEALTH["Power Bus Health<br/><i>POWER / ENERGY</i>"]:::ext
  CO_LINK_HEALTH["Link Health<br/><i>COMMUNICATION</i>"]:::ext
  C_ATT["Attitude Control<br/><i>FLIGHT CONTROL (yazılım soyutlaması; kazanç içermez)</i>"]:::ext
  BUS_HEALTH["Health Bus<br/><i>DATA BUS (mantıksal)</i>"]:::ext
  SUP_SYSTEM["System Supervisor<br/><i>SYSTEM SUPERVISION</i>"]:::ext
  FDR_FDIR["FDIR Recorder<br/><i>FLIGHT DATA RECORDER</i>"]:::ext
  SEN_HEALTH -.->|"kanal sağlıkları"| FDIR_SENSOR
  NAV_HEALTH -.->|"NavigationHealth"| FDIR_NAV
  MC_HEALTH -.->|"öneri akışı"| FDIR_MC
  FDIR_SURFACE_MON -.->|"yüzey sağlığı"| ACT_HEALTH_GATE
  FCC_ISOLATION -.->|"şerit durumları"| FDIR_FCC
  SEN_RPM -->|"ölçülen devir"| FDIR_MOTOR_MON
  FDIR_MOTOR_MON --> ACT_MOTOR_HEALTH
  FDIR_MOTOR_MON -.->|"motor durumları"| FDIR_MOTOR
  SEN_ACT_POS --> FDIR_SURFACE_MON
  FDIR_SURFACE_MON -.->|"yüzey durumları"| FDIR_ACTUATOR
  AL_AUTHORITY -.->|"hover fizibilitesi"| FDIR_MOTOR
  EN_MANAGER -.->|"EnergyState"| FDIR_ENERGY
  EN_RESERVE -.->|"rezerv uyarısı"| FDIR_ENERGY
  EN_BUS_HEALTH -.->|"güç açığı"| FDIR_ENERGY
  CO_LINK_HEALTH -.->|"bağlantı"| FDIR_COMM
  FDIR_SENSOR -.->|"FdirReport"| FDIR_SUP
  FDIR_NAV -.->|"FdirReport"| FDIR_SUP
  FDIR_FCC -.->|"FdirReport"| FDIR_SUP
  FDIR_MOTOR -.->|"FdirReport"| FDIR_SUP
  FDIR_ACTUATOR -.->|"FdirReport"| FDIR_SUP
  FDIR_ENERGY -.->|"FdirReport"| FDIR_SUP
  FDIR_COMM -.->|"FdirReport"| FDIR_SUP
  FDIR_MC -.->|"FdirReport"| FDIR_SUP
  FDIR_REPORT -.->|"biçim"| FDIR_SUP
  FDIR_SUP -.->|"8 rapor"| VH_MANAGER
  VH_CONTROL_AUTH -.->|"kontrol otoritesi"| VH_MANAGER
  C_ATT -.->|"controllable"| VH_CONTROL_AUTH
  VH_MANAGER -.-> VH_LEVEL
  VH_NOT_MODELED -.-> VH_MANAGER
  VH_LEVEL -.->|"VehicleHealth"| BUS_HEALTH
  FDIR_SUP -.->|"FDIR raporları"| SUP_SYSTEM
  FDIR_SUP --> FDR_FDIR
```
<!-- END GENERATED: view-fdir-health -->

## Bileşen matrisi

<!-- BEGIN GENERATED: matrix-fdir-health -->
#### FDIR

| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | Code Location | Implementation Status |
|---|---|---|---|---|---|---|---|
| **FDIR Supervisor** `FDIR_SUP` | Sekiz alan FDIR'ini çalıştırma, raporları birleştirme | alan girdileri | 8 FdirReport | NOMINAL/DEGRADED/FAILED/UNKNOWN | Bilgisi olmayan alan UNKNOWN raporlar | `simurg/fdir/vehicle_health.py::VehicleHealthModel` | IMPLEMENTED |
| **Sensor FDIR** `FDIR_SENSOR` | Tespit, yalıtım, sınıf, güven, sağlık, önerilen bozulma | Kanal sağlıkları | FdirReport | NOMINAL/DEGRADED/FAILED/UNKNOWN | Gözlenmeyen durum -> UNKNOWN (NOMINAL değil) | `simurg/fdir/reports.py::sensor_fdir` | IMPLEMENTED |
| **Navigation FDIR** `FDIR_NAV` | Tespit, yalıtım, sınıf, güven, sağlık, önerilen bozulma | NavigationSolution | FdirReport | NOMINAL/DEGRADED/FAILED/UNKNOWN | Gözlenmeyen durum -> UNKNOWN (NOMINAL değil) | `simurg/fdir/reports.py::navigation_fdir` | IMPLEMENTED |
| **FCC FDIR** `FDIR_FCC` | Tespit, yalıtım, sınıf, güven, sağlık, önerilen bozulma | Şerit durumları | FdirReport | NOMINAL/DEGRADED/FAILED/UNKNOWN | Gözlenmeyen durum -> UNKNOWN (NOMINAL değil) | `simurg/fdir/reports.py::fcc_fdir` | IMPLEMENTED |
| **Motor FDIR** `FDIR_MOTOR` | Tespit, yalıtım, sınıf, güven, sağlık, önerilen bozulma | Motor durumları + hover fizibilitesi | FdirReport | NOMINAL/DEGRADED/FAILED/UNKNOWN | Gözlenmeyen durum -> UNKNOWN (NOMINAL değil) | `simurg/fdir/reports.py::motor_fdir` | IMPLEMENTED |
| **Actuator FDIR** `FDIR_ACTUATOR` | Tespit, yalıtım, sınıf, güven, sağlık, önerilen bozulma | Yüzey durumları | FdirReport | NOMINAL/DEGRADED/FAILED/UNKNOWN | Gözlenmeyen durum -> UNKNOWN (NOMINAL değil) | `simurg/fdir/reports.py::actuator_fdir` | IMPLEMENTED |
| **Energy FDIR** `FDIR_ENERGY` | Tespit, yalıtım, sınıf, güven, sağlık, önerilen bozulma | EnergyState, rezerv, güç açığı | FdirReport | NOMINAL/DEGRADED/FAILED/UNKNOWN | Gözlenmeyen durum -> UNKNOWN (NOMINAL değil) | `simurg/fdir/reports.py::energy_fdir` | IMPLEMENTED |
| **Communication FDIR** `FDIR_COMM` | Tespit, yalıtım, sınıf, güven, sağlık, önerilen bozulma | Bağlantı durumu | FdirReport | NOMINAL/DEGRADED/FAILED/UNKNOWN | Gözlenmeyen durum -> UNKNOWN (NOMINAL değil) | `simurg/fdir/reports.py::communication_fdir` | IMPLEMENTED |
| **Mission Computer FDIR** `FDIR_MC` | Tespit, yalıtım, sınıf, güven, sağlık, önerilen bozulma | Öneri akışı geçerliliği | FdirReport | NOMINAL/DEGRADED/FAILED/UNKNOWN | Gözlenmeyen durum -> UNKNOWN (NOMINAL değil) | `simurg/fdir/reports.py::mission_computer_fdir` | IMPLEMENTED |
| **Motor Monitor (CUSUM)** `FDIR_MOTOR_MON` | Devir artığı CUSUM + verim EMA | beklenen/ölçülen devir | ComponentHealth | NOMINAL/DEGRADED/FAILED/UNKNOWN | Sabit kısmi hasar DEGRADED kalır; FAILED mandallı | `simurg/fdir/monitor.py::MotorHealthMonitor` | IMPLEMENTED |
| **Surface Monitor** `FDIR_SURFACE_MON` | Komut-konum artığı kalıcılığı | beklenen/ölçülen konum | ComponentHealth | NOMINAL/FAILED | Kalıcı artık -> FAILED | `simurg/fdir/monitor.py::SurfaceMonitor` | PARTIAL — Yüzey verim kaybı konumdan gözlenemez |
| **FDIR Report Format** `FDIR_REPORT` | Standart rapor: tespit/yalıtım/sınıf/güven/sağlık/öneri | - | FdirReport | durumsuz (n/a) | n/a | `simurg/fdir/reports.py::FdirReport` | IMPLEMENTED |

#### VEHICLE HEALTH

| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | Code Location | Implementation Status |
|---|---|---|---|---|---|---|---|
| **Vehicle Health Manager** `VH_MANAGER` | Alan raporlarını araç seviyesine birleştirme | 8 FdirReport + kontrol otoritesi | VehicleHealth | NOMINAL/DEGRADED/CONTINGENCY/CRITICAL/UNKNOWN | UNKNOWN asla NOMINAL değil; değişim VEHICLE_HEALTH_CHANGED olayı | `simurg/fdir/vehicle_health.py::VehicleHealthModel` | IMPLEMENTED |
| **Health Level Classifier** `VH_LEVEL` | CRITICAL > CONTINGENCY > UNKNOWN > DEGRADED > NOMINAL | alan durumları | seviye + reasons[] | durumsuz (n/a) | n/a (saf fonksiyon) | `simurg/fdir/vehicle_health.py::classify` | IMPLEMENTED |
| **Control Authority Domain** `VH_CONTROL_AUTH` | Kontrol edilebilirlik + askı otoritesi | controllable, hover marjı | kontrol alanı sağlığı | NOMINAL/DEGRADED/FAILED/UNKNOWN | Kontrol kaybı -> CRITICAL | `simurg/fdir/vehicle_health.py::VehicleHealthModel` | IMPLEMENTED |
| **Not-Modeled Register** `VH_NOT_MODELED` | Modellenmeyen alanların açık listesi (termal, IMU) | - | not_modeled | durumsuz (n/a) | 'Modellenmedi' != 'sağlıklı' ayrımı korunur | `simurg/fdir/vehicle_health.py::NOT_MODELED` | IMPLEMENTED |
<!-- END GENERATED: matrix-fdir-health -->
