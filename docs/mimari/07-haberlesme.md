# 07 — COMMUNICATION ARCHITECTURE

> Sivil mühendislik referans mimarisi — yazılım/güvenlik/simülasyon düzeyi.
> Uçuşa hazır donanım, kablolama, ESC/motor ayarı ya da kontrol kazancı içermez.
> Ana belge: [15 — Master System Architecture](../15-sistem-mimarisi.md).
> Diyagram ve tablolar `python -m simurg.architecture --update-all` ile üretilir.

## Mesaj yolu

```mermaid
flowchart LR
  GCS["Ground Segment"] == istek ==> GL["Ground Link"] ==> MV["Message Validator"] ==> SQ["Sequence Monitor"] ==> CR["Command Router"]
  CR == mod isteği ==> FSM["Flight Mode Machine"]
  CR == görev güncellemesi ==> MM["Mission Manager"]
  TB["Telemetry Bus"] --> TR["Telemetry Router"] --> GL
  GL -.-> HB["Heartbeat Monitor"] -.-> LH["Link Health"] -.-> FO["Failover Manager"]
  LQ["Link Quality"] -.-> LH
```

* Yer segmenti yalnızca İSTEK gönderir; mod değişimi Flight Mode Machine'in
  koruma koşullarına tabidir.
* Bugün modellenen: C2 var/yok + kesinti süresi (`simurg/sim/link.py`) ve
  haberleşme FDIR'i. Mesaj doğrulama, sıra izleme, bağlantı kalitesi ve
  failover PLANNED'dır.
* Kapsam dışı: gerçek radyo frekansları, şifreleme anahtarları, saldırı,
  karıştırma (jamming) ya da kaçınma (evasion) teknikleri.

## Diyagram

<!-- BEGIN GENERATED: view-communication -->
```mermaid
flowchart LR
  classDef implemented fill:#d7f5dd,stroke:#1a7f37,color:#0b3d1a;
  classDef partial fill:#fff4c2,stroke:#9a6700,color:#3d2e00;
  classDef unvalidated fill:#ffe1c7,stroke:#bc4c00,color:#4d1f00;
  classDef planned fill:#eef0f3,stroke:#8c959f,color:#57606a,stroke-dasharray: 4 3;
  classDef gate fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a,stroke-width:3px;
  classDef ext fill:#ffffff,stroke:#8c959f,color:#57606a;
  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;
  subgraph COMM["COMMUNICATION"]
    direction TB
    subgraph COMM_LINK["Bağlantılar"]
      CO_GROUND["Ground Link"]:::implemented
      CO_V2V["Vehicle-to-Vehicle Link"]:::planned
    end
    subgraph COMM_PROC["Mesaj işleme"]
      CO_MSG_VALID["Message Validator"]:::planned
      CO_SEQ["Sequence Monitor"]:::planned
      CO_CMD_ROUTER["Command Router"]:::planned
      CO_TLM_ROUTER["Telemetry Router"]:::planned
    end
    subgraph COMM_HEALTH["Bağlantı sağlığı"]
      CO_HEARTBEAT["Heartbeat Monitor"]:::implemented
      CO_LINK_QUALITY["Link Quality"]:::planned
      CO_LINK_HEALTH["Link Health"]:::implemented
      CO_FAILOVER["Failover Manager"]:::planned
    end
  end
  subgraph GCS["GROUND SEGMENT"]
    direction TB
    GCS_OPERATOR["Operator Console"]:::planned
    GCS_MISSION_PLAN["Mission Planning"]:::partial
    GCS_HEALTH_VIEW["Health / RTA / Nav Panels"]:::planned
    GCS_REPLAY["Replay & Log Viewer"]:::partial
    GCS_FLEET["Fleet / Swarm View"]:::planned
  end
  MD_FSM["Flight Mode Machine<br/><i>MODE / CONTINGENCY MANAGEMENT</i>"]:::ext
  MC_MISSION_MGR["Mission Manager<br/><i>MISSION COMPUTER (yalnızca öneri; uçuş-kritik değil)</i>"]:::ext
  MC_SWARM["Swarm Coordination<br/><i>MISSION COMPUTER (yalnızca öneri; uçuş-kritik değil)</i>"]:::ext
  BUS_TLM["Telemetry Bus<br/><i>DATA BUS (mantıksal)</i>"]:::ext
  FDIR_COMM["Communication FDIR<br/><i>FDIR</i>"]:::ext
  MD_CONTINGENCY["Contingency Manager<br/><i>MODE / CONTINGENCY MANAGEMENT</i>"]:::ext
  PF_COMM["Communication Check<br/><i>PREFLIGHT SUPERVISOR</i>"]:::ext
  PF_MISSION["Mission Validation<br/><i>PREFLIGHT SUPERVISOR</i>"]:::ext
  SUP_SYSTEM["System Supervisor<br/><i>SYSTEM SUPERVISION</i>"]:::ext
  FDR_EXPLAIN["Decision Explainer<br/><i>FLIGHT DATA RECORDER</i>"]:::ext
  DT_COMMS["Communication Model<br/><i>DIGITAL TWIN</i>"]:::ext
  DT_METRICS["Metrics<br/><i>DIGITAL TWIN</i>"]:::ext
  GCS_OPERATOR ==>|"istek uplink"| CO_GROUND
  GCS_MISSION_PLAN ==>|"görev"| CO_GROUND
  CO_GROUND ==>|"uplink"| CO_MSG_VALID
  CO_MSG_VALID ==> CO_SEQ
  CO_SEQ ==> CO_CMD_ROUTER
  CO_CMD_ROUTER ==>|"operatör mod isteği"| MD_FSM
  CO_CMD_ROUTER ==>|"görev güncellemesi"| MC_MISSION_MGR
  CO_TLM_ROUTER -->|"downlink"| CO_GROUND
  CO_GROUND -->|"telemetri"| GCS_HEALTH_VIEW
  CO_V2V -->|"komşu durumları"| MC_SWARM
  CO_GROUND -.-> CO_HEARTBEAT
  CO_HEARTBEAT -.->|"kesinti süresi"| CO_LINK_HEALTH
  CO_LINK_QUALITY -.-> CO_LINK_HEALTH
  CO_LINK_HEALTH -.-> CO_FAILOVER
  CO_FAILOVER -.->|"yol seçimi"| CO_GROUND
  BUS_TLM --> CO_TLM_ROUTER
  CO_LINK_HEALTH -.->|"bağlantı"| FDIR_COMM
  CO_LINK_HEALTH -.->|"C2 kesinti süresi"| MD_CONTINGENCY
  CO_LINK_HEALTH -.-> PF_COMM
  GCS_MISSION_PLAN -.->|"görev"| PF_MISSION
  CO_LINK_HEALTH -.->|"haberleşme"| SUP_SYSTEM
  FDR_EXPLAIN --> GCS_REPLAY
  DT_COMMS -->|"bağlantı durumu"| CO_GROUND
  DT_METRICS -->|"sonuçlar"| GCS_REPLAY
```
<!-- END GENERATED: view-communication -->

## Bileşen matrisi

<!-- BEGIN GENERATED: matrix-communication -->
#### GROUND SEGMENT

| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | Code Location | Implementation Status |
|---|---|---|---|---|---|---|---|
| **Operator Console** `GCS_OPERATOR` | Operatör görünümü ve komut girişi (yalnızca istek) | telemetri, olaylar | görev/mod isteği | NOMINAL/DEGRADED/FAILED/UNKNOWN | Konsol yok -> araç son geçerli görevde kalır; bağlantı kaybı kuralı işler | — | PLANNED |
| **Mission Planning** `GCS_MISSION_PLAN` | Görev ve geofence tanımı | operatör | görev profili | durumsuz (n/a) | Geçersiz görev uçuş öncesi denetimde reddedilir | `simurg/sim/scenario.py::MissionProfile` | PARTIAL — Senaryo dosyasıyla tanımlanır |
| **Health / RTA / Nav Panels** `GCS_HEALTH_VIEW` | Sağlık, RTA, nav bütünlüğü, enerji görünümü | telemetri | operatör uyarıları | durumsuz (n/a) | Görünüm yok -> karar araç üzerinde kalır | — | PLANNED |
| **Replay & Log Viewer** `GCS_REPLAY` | Kaydın zaman çizelgesi ve açıklaması | simurg.sim-log | zaman çizelgesi | durumsuz (n/a) | Bilinmeyen şema reddedilir | `simurg/sim/__main__.py::main` | PARTIAL — CLI: python -m simurg.sim replay |
| **Fleet / Swarm View** `GCS_FLEET` | Çoklu araç görünümü | telemetri | görünüm | durumsuz (n/a) | n/a | — | PLANNED |

#### COMMUNICATION

| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | Code Location | Implementation Status |
|---|---|---|---|---|---|---|---|
| **Ground Link** `CO_GROUND` | Yer bağlantısı soyutlaması (C2 var/yok) | uplink/downlink | mesajlar, bağlantı durumu | NOMINAL/DEGRADED/FAILED/UNKNOWN | Kayıp -> LINK_LOST olayı, 30 s sonra RETURN kuralı | `simurg/sim/link.py::LinkModel` | IMPLEMENTED |
| **Vehicle-to-Vehicle Link** `CO_V2V` | Araçlar arası mesajlaşma soyutlaması | mesajlar | komşu durumları | NOMINAL/DEGRADED/FAILED/UNKNOWN | Kayıp -> sürü koordinasyonu öneri üretmez | — | PLANNED |
| **Message Validator** `CO_MSG_VALID` | Şema/aralık denetimi | uplink | geçerli mesaj | NOMINAL/DEGRADED/FAILED/UNKNOWN | Geçersiz mesaj düşürülür ve olay üretilir | — | PLANNED |
| **Sequence Monitor** `CO_SEQ` | Sıra numarası / tekrar / kayıp denetimi | mesajlar | sıra durumu | NOMINAL/DEGRADED/FAILED/UNKNOWN | Tekrar/eski mesaj reddedilir | — | PLANNED |
| **Command Router** `CO_CMD_ROUTER` | Doğrulanmış yer isteklerini hedefe yönlendirme | geçerli mesaj | mod/görev isteği | NOMINAL/DEGRADED/FAILED/UNKNOWN | Yönlendirilemeyen istek uygulanmaz | — | PLANNED |
| **Telemetry Router** `CO_TLM_ROUTER` | Telemetrinin bağlantılara yönlendirilmesi | telemetri yolu | downlink | NOMINAL/DEGRADED/FAILED/UNKNOWN | Telemetri düşer; araç davranışı etkilenmez | — | PLANNED |
| **Heartbeat Monitor** `CO_HEARTBEAT` | Bağlantı yaşam sinyali ve kesinti süresi | bağlantı | kesinti süresi | NOMINAL/DEGRADED/FAILED/UNKNOWN | Kalp atışı yok -> kesinti zamanlayıcısı başlar | `simurg/sim/link.py::LinkModel` | IMPLEMENTED |
| **Link Quality** `CO_LINK_QUALITY` | Gecikme/kayıp ölçümü | bağlantı | kalite metriği | NOMINAL/DEGRADED/FAILED/UNKNOWN | Ölçüm yok -> kalite UNKNOWN | — | PLANNED |
| **Link Health** `CO_LINK_HEALTH` | C2 var/yok + kesinti süresi -> haberleşme FDIR | kalp atışı | bağlantı sağlığı | NOMINAL/DEGRADED/FAILED/UNKNOWN | C2 yok -> FAILED (iyimser varsayım yok) | `simurg/fdir/reports.py::communication_fdir` | IMPLEMENTED |
| **Failover Manager** `CO_FAILOVER` | Yedek bağlantıya geçiş | bağlantı sağlığı | yol seçimi | NOMINAL/DEGRADED/FAILED/UNKNOWN | Yedek yok -> bağlantı kaybı kuralı Yedeklilik: planlanan çift bağlantı. | — | PLANNED |
<!-- END GENERATED: matrix-communication -->
