# 11 — MISSION COMPUTER (öneri katmanı)

> Sivil mühendislik referans mimarisi — yazılım/güvenlik/simülasyon düzeyi.
> Uçuşa hazır donanım, kablolama, ESC/motor ayarı ya da kontrol kazancı içermez.
> Ana belge: [15 — Master System Architecture](../15-sistem-mimarisi.md).
> Diyagram ve tablolar `python -m simurg.architecture --update-all` ile üretilir.

Görev bilgisayarı **uçuş-kritik değildir**. Mission Manager, High-Level
Planner, Search Planner, Perception, Mission AI, Mapping, Swarm Coordination
ve Mission Health bloklarının tek çıkışı `CommandProposal`'dır (ve Flight
Mode Machine'e mod İSTEĞİ). AI → eyleyici doğrudan yolu yoktur; bu,
mimari kayıtta yetki yolu taramasıyla (`test_architecture`) ve kodda içe
aktarma taramasıyla (`test_safety_invariants`) zorlanır.

Görev bilgisayarı sağlığı öneri akışından gözlenir: geçersiz/bayat öneri →
DEGRADED; 3 s'den uzun sürerse FAILED → araç sağlığı CONTINGENCY. Bu sürede
RTA yalnızca güvenlik kontrolcüsünü doğrular (`mission_computer_failure`
senaryosu).

Kapsam: arama-kurtarma, afet gözlemi, çevre izleme, altyapı denetimi.
Hedef takibi, insan/araç takibi ya da yük bırakma yoktur.

## Diyagram

<!-- BEGIN GENERATED: view-mission-computer -->
```mermaid
flowchart LR
  classDef implemented fill:#d7f5dd,stroke:#1a7f37,color:#0b3d1a;
  classDef partial fill:#fff4c2,stroke:#9a6700,color:#3d2e00;
  classDef unvalidated fill:#ffe1c7,stroke:#bc4c00,color:#4d1f00;
  classDef planned fill:#eef0f3,stroke:#8c959f,color:#57606a,stroke-dasharray: 4 3;
  classDef gate fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a,stroke-width:3px;
  classDef ext fill:#ffffff,stroke:#8c959f,color:#57606a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  subgraph MC["MISSION COMPUTER (yalnızca öneri; uçuş-kritik değil)"]
    direction TB
    MC_MISSION_MGR["Mission Manager"]:::implemented
    MC_PLANNER["High-Level Planner"]:::partial
    MC_SEARCH["Search Planner"]:::planned
    MC_PERCEPTION["Perception"]:::planned
    MC_AI["Mission AI"]:::planned
    MC_MAPPING["Mapping"]:::planned
    MC_SWARM["Swarm Coordination"]:::partial
    MC_PROPOSAL["CommandProposal Output"]:::implemented
    MC_HEALTH["Mission Health"]:::implemented
  end
  CO_CMD_ROUTER["Command Router<br/><i>COMMUNICATION</i>"]:::ext
  CO_V2V["Vehicle-to-Vehicle Link<br/><i>COMMUNICATION</i>"]:::ext
  BUS_STATE["State Bus<br/><i>DATA BUS (mantıksal)</i>"]:::ext
  G_WAYPOINT["Waypoint Guidance<br/><i>GUIDANCE</i>"]:::ext
  MD_FSM["Flight Mode Machine<br/><i>MODE / CONTINGENCY MANAGEMENT</i>"]:::ext
  G_MISSION["Mission Guidance<br/><i>GUIDANCE</i>"]:::ext
  G_LOITER["Loiter / Hold Guidance<br/><i>GUIDANCE</i>"]:::ext
  G_RETURN["Return Guidance<br/><i>GUIDANCE</i>"]:::ext
  CV_PROPOSAL["Proposal Envelope<br/><i>COMMAND VALIDATION</i>"]:::ext
  CV_VALIDATOR["Command Validator<br/><i>COMMAND VALIDATION</i>"]:::ext
  FDIR_MC["Mission Computer FDIR<br/><i>FDIR</i>"]:::ext
  EN_RESERVE["Reserve Estimator<br/><i>POWER / ENERGY</i>"]:::ext
  DT_FAULTS["Fault Schedule / Injection<br/><i>DIGITAL TWIN</i>"]:::ext
  CO_CMD_ROUTER ==>|"görev güncellemesi"| MC_MISSION_MGR
  CO_V2V -->|"komşu durumları"| MC_SWARM
  BUS_STATE -->|"durum"| MC_MISSION_MGR
  MC_PLANNER -->|"rota"| MC_MISSION_MGR
  MC_SEARCH -->|"desen"| MC_PLANNER
  MC_PERCEPTION --> MC_AI
  MC_AI --> MC_MAPPING
  MC_MAPPING -->|"harita"| MC_PLANNER
  MC_SWARM -->|"atanan görevler"| MC_PLANNER
  MC_AI ==>|"öneri"| MC_PROPOSAL
  MC_MISSION_MGR ==>|"aktif hedef"| G_WAYPOINT
  MC_MISSION_MGR ==>|"nominal mod isteği"| MD_FSM
  G_MISSION ==>|"Command"| MC_PROPOSAL
  G_LOITER ==>|"Command"| MC_PROPOSAL
  G_RETURN ==>|"Command"| MC_PROPOSAL
  MC_PROPOSAL ==>|"CommandProposal"| CV_PROPOSAL
  CV_VALIDATOR -.->|"red/kabul"| MC_HEALTH
  MC_HEALTH -.->|"öneri akışı"| FDIR_MC
  EN_RESERVE -.->|"rezerv kısıtı"| MC_MISSION_MGR
  DT_FAULTS -.->|"öneri arızası"| MC_AI
```
<!-- END GENERATED: view-mission-computer -->

## Bileşen matrisi

<!-- BEGIN GENERATED: matrix-mission-computer -->
#### MISSION COMPUTER (yalnızca öneri; uçuş-kritik değil)

| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | Code Location | Implementation Status |
|---|---|---|---|---|---|---|---|
| **Mission Manager** `MC_MISSION_MGR` *(öneri)* | Görev ilerleyişi; nominal mod İSTEĞİ (FSM'e) | durum, enerji rezervi, nav bütünlüğü | mod isteği, hedef | durumsuz (n/a) | Arıza/hatalı çıktı -> öneri doğrulayıcıda reddedilir; uçuş güvenliği RTA + güvenlik kontrolcüsünde | `simurg/sim/mission.py::MissionManager` | IMPLEMENTED |
| **High-Level Planner** `MC_PLANNER` *(öneri)* | Görev hedeflerinden ara nokta rotası | görev | ara noktalar | durumsuz (n/a) | Arıza/hatalı çıktı -> öneri doğrulayıcıda reddedilir; uçuş güvenliği RTA + güvenlik kontrolcüsünde | `simurg/sim/scenario.py::MissionProfile` | PARTIAL — Rota senaryoda sabit; planlayıcı yok |
| **Search Planner** `MC_SEARCH` *(öneri)* | Arama-tarama deseni (şerit/spiral) | arama alanı | ara noktalar | durumsuz (n/a) | Arıza/hatalı çıktı -> öneri doğrulayıcıda reddedilir; uçuş güvenliği RTA + güvenlik kontrolcüsünde | — | PLANNED |
| **Perception** `MC_PERCEPTION` *(öneri)* | Gözlem verisinden olay çıkarımı (sivil gözlem) | kamera | algı olayları | NOMINAL/DEGRADED/FAILED/UNKNOWN | Arıza/hatalı çıktı -> öneri doğrulayıcıda reddedilir; uçuş güvenliği RTA + güvenlik kontrolcüsünde | — | PLANNED |
| **Mission AI** `MC_AI` *(öneri)* | YZ çıkarımı -> yalnızca öneri | algı, durum | öneri | NOMINAL/DEGRADED/FAILED/UNKNOWN | Arıza/hatalı çıktı -> öneri doğrulayıcıda reddedilir; uçuş güvenliği RTA + güvenlik kontrolcüsünde | — | PLANNED |
| **Mapping** `MC_MAPPING` *(öneri)* | Görev haritası | algı + konum | harita | durumsuz (n/a) | Arıza/hatalı çıktı -> öneri doğrulayıcıda reddedilir; uçuş güvenliği RTA + güvenlik kontrolcüsünde | — | PLANNED |
| **Swarm Coordination** `MC_SWARM` *(öneri)* | Enerji farkındalıklı görev dağıtımı (CBBA referansı) | ajanlar, görevler | görev ataması | durumsuz (n/a) | Arıza/hatalı çıktı -> öneri doğrulayıcıda reddedilir; uçuş güvenliği RTA + güvenlik kontrolcüsünde | `simurg/swarm/auction.py::allocate` | PARTIAL — Simülasyon motoruna bağlı değil |
| **CommandProposal Output** `MC_PROPOSAL` *(öneri)* | Tek çıkış: zaman damgalı, kaynaklı öneri zarfı | güdüm çıktısı | CommandProposal | durumsuz (n/a) | Bayat/geçersiz zarf doğrulayıcıda reddedilir | `simurg/safety/command_validator.py::CommandProposal` | IMPLEMENTED |
| **Mission Health** `MC_HEALTH` *(öneri)* | Görev bilgisayarı sağlığı (öneri akışı geçerliliği) | doğrulayıcı sonuçları | görev bilg. sağlığı | NOMINAL/DEGRADED/FAILED/UNKNOWN | Kalıcı geçersiz öneri (>3 s) -> FAILED -> CONTINGENCY | `simurg/fdir/reports.py::mission_computer_fdir` | IMPLEMENTED |
<!-- END GENERATED: matrix-mission-computer -->
