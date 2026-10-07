"""SİMURG sistem-sistemleri (system-of-systems) mimarisinin bileşen kaydı.

Tek doğruluk kaynağı: docs/15-sistem-mimarisi.md içindeki diyagramlar ve
bileşen matrisi bu kayıttan ÜRETİLİR (`python -m simurg.architecture
--update docs/15-sistem-mimarisi.md`) ve `tests/test_architecture.py`
belge ile kaydın birebir aynı olduğunu, her kod referansının gerçekten
var olduğunu ve yetki değişmezlerini doğrular.

Durum anlamı:
  IMPLEMENTED  kodda var, simülasyona bağlı, testli
  PARTIAL      basitleştirilmiş / tek şeritli / simülasyona henüz bağlı değil
  PLANNED      yalnızca mimaride (kod yok)

Bu kayıt bir yazılım/dijital ikiz mimari referansıdır; uçuşa hazır donanım
kablolaması, sürücü protokolü ya da kontrol kazancı içermez.
"""

from __future__ import annotations

from .model import Architecture, Component, Edge, EdgeKind, Group, Status

I, P, X = Status.IMPLEMENTED, Status.PARTIAL, Status.PLANNED
D, CMD, S = EdgeKind.DATA, EdgeKind.COMMAND, EdgeKind.SUPERVISORY

HS = "NOMINAL/DEGRADED/FAILED/UNKNOWN"

GROUPS: tuple[Group, ...] = (
    Group("SEN", "SENSORS", (("SEN_INS", "INERTIAL"), ("SEN_AIR", "AIR DATA"),
                             ("SEN_POS", "POSITION / NAVIGATION SOURCES"),
                             ("SEN_VH", "VEHICLE HEALTH SENSORS"), ("SEN_EN", "ENERGY SENSORS"),
                             ("SEN_PIPE", "SENSOR PIPELINE"))),
    Group("MC", "MISSION COMPUTER (yalnızca öneri, uçuş yetkisi yok)",
          (("MC_PLAN", "Görev planlama"), ("MC_PERC", "Algılama ve YZ"), ("MC_SWARM", "Sürü"))),
    Group("NAV", "NAVIGATION", (("NAV_PIPE", "Navigasyon hattı"), ("NAV_MON", "Kaynak izleyicileri"))),
    Group("GNC", "GNC", (("GNC_G", "GUIDANCE"), ("GNC_C", "CONTROL"))),
    Group("RTA", "SIMPLEX RTA", (("RTA_PATH", "Karar hattı"), ("RTA_SUPPORT", "Destek"))),
    Group("LANEA", "FLIGHT COMPUTER LANE A"),
    Group("LANEB", "FLIGHT COMPUTER LANE B"),
    Group("LANEC", "INDEPENDENT MONITOR (LANE C)"),
    Group("LANEM", "LANE MANAGEMENT"),
    Group("ALLOC", "CONTROL ALLOCATION"),
    Group("ACT", "ACTUATORS (simülasyon soyutlaması)", (("ACT_M", "Motor Group"),
                                                        ("ACT_E", "Elevon Group"))),
    Group("FDIR", "FDIR", (("FDIR_DOM", "Alan FDIR"), ("FDIR_PIPE", "Ortak FDIR hattı"))),
    Group("EN", "ENERGY", (("EN_SRC", "Kaynak modelleri"), ("EN_MGMT", "Güç yönetimi"),
                           ("EN_SUPV", "Enerji gözetimi"))),
    Group("COMM", "COMMUNICATION"),
    Group("MODE", "MODE & CONTINGENCY"),
    Group("PRE", "PREFLIGHT SUPERVISOR"),
    Group("SUP", "SYSTEM SUPERVISOR"),
    Group("BUS", "VEHICLE DATA BUS"),
    Group("TIME", "TIME & SYNCHRONIZATION"),
    Group("CFG", "CONFIGURATION MANAGER"),
    Group("FDR", "FLIGHT DATA RECORDER"),
    Group("DT", "DIGITAL TWIN"),
    Group("GCS", "GROUND CONTROL STATION"),
)

_C: list[Component] = []


def c(id: str, name: str, group: str, resp: str, inp: str, out: str, health: str,
      status: Status, code: tuple[str, ...] = (), sub: str = "", proposal: bool = False,
      note: str = "") -> None:
    _C.append(Component(id, name, group, resp, inp, out, health, status, code, sub, proposal, note))


# ============================================================ SENSORS
for k in "ABC":
    c(f"SEN_IMU_{k}", f"IMU {k}", "SEN", f"Şerit {k} için bağımsız açısal hız/ivme ölçümü",
      "araç hareketi", "ham ivme + açısal hız", HS, X, sub="SEN_INS",
      note="Simülasyonda tutum kusursuz kestirici varsayımıyla gerçek durumdan alınır")
c("SEN_ACCEL_PROC", "Accelerometer Processing", "SEN", "İvme ölçümünü filtreleme/ölçekleme",
  "koşullandırılmış ivme", "işlenmiş ivme", HS, X, sub="SEN_INS")
c("SEN_GYRO_PROC", "Gyro Processing", "SEN", "Açısal hız ölçümünü filtreleme",
  "koşullandırılmış açısal hız", "işlenmiş açısal hız", HS, X, sub="SEN_INS")
c("SEN_BIAS_EST", "IMU Bias Estimator", "SEN", "Jiroskop/ivmeölçer sapma kestirimi",
  "işlenmiş IMU, nav çözümü", "sapma düzeltmeli IMU", HS, X, sub="SEN_INS")
c("SEN_VIB_MON", "Vibration Monitor", "SEN", "Titreşim spektrumu izleme (pervane/motor hasarı göstergesi)",
  "işlenmiş ivme", "titreşim sağlık göstergesi", HS, X, sub="SEN_INS")
c("SEN_BARO", "Barometric Altitude", "SEN", "Barometrik irtifa ölçümü",
  "statik basınç", "irtifa (gürültülü)", "dropout -> geçersiz ölçüm", I,
  ("simurg/sim/sensors.py::SensorModel", "simurg/sim/airdata.py::AirDataSystem"), sub="SEN_AIR")
c("SEN_AIRSPEED", "Airspeed Estimate", "SEN", "Pitot tabanlı hava hızı",
  "dinamik basınç", "hava hızı (gürültülü)", "dropout -> yer hızı geri dönüşü + olay", I,
  ("simurg/sim/airdata.py::AirDataSystem",), sub="SEN_AIR")
c("SEN_TEMP", "Air Temperature", "SEN", "Dış hava sıcaklığı", "sıcaklık sensörü",
  "sıcaklık", HS, P, ("simurg/sim/environment.py::EnvironmentState",), sub="SEN_AIR",
  note="Ortam modelinde sabit değer; sensör modeli yok")
c("SEN_PRESS_VALID", "Pressure Validation", "SEN", "Basınç ölçümünün sonluluk/geçerlilik denetimi",
  "baro + pitot ölçümü", "geçerli/geçersiz bayrağı", "geçersiz -> açık geri dönüş", I,
  ("simurg/sim/airdata.py::AirDataSystem",), sub="SEN_AIR")
for sid, nm, resp in (("GNSS", "GNSS", "Çok takımyıldızlı mutlak konum"),
                      ("VIO", "VIO", "Görsel-ataletsel göreli konum"),
                      ("TRN", "TRN", "Arazi referanslı konum"),
                      ("MAGNAV", "MagNav", "Manyetik anomali haritası ile konum")):
    c(f"SEN_{sid}", nm, "SEN", resp, "ortam", "konum + nominal kovaryans",
      "dropout / bias / gürültü arızası", I,
      ("simurg/sim/sensors.py::SimulatedPositionProvider",), sub="SEN_POS")
c("SEN_CELESTIAL", "Celestial Navigation", "SEN", "Güneş/yıldız ile yön sınırlama",
  "kamera", "yön (heading) gözlemi", HS, X, sub="SEN_POS")
c("SEN_INERTIAL_PROP", "Inertial Propagation", "SEN", "Kaynak yokken son çözümü hızla ilerletme",
  "son güvenilir çözüm, hız", "ilerletilmiş konum, büyüyen PL", "integrity_ok=False (asla varsayılmaz)",
  I, ("simurg/nav/providers.py::NavigationSystem",), sub="SEN_POS")
c("SEN_ESC_TLM", "ESC Telemetry", "SEN", "Motor sürücü telemetrisinin toplanması (soyutlama)",
  "motor durumu", "devir/akım/sıcaklık paketi", HS, P,
  ("simurg/sim/actuators.py::rpm_from_output",), sub="SEN_VH", note="Yalnızca devir modellenir")
c("SEN_RPM", "Motor RPM", "SEN", "Motor devir ölçümü", "eyleyici çıkışı", "devir (gürültülü)",
  "dropout -> FDIR güncellenmez", I, ("simurg/sim/sensors.py::SensorModel",), sub="SEN_VH")
c("SEN_MOTOR_CURRENT", "Motor Current", "SEN", "Faz akımı ölçümü", "motor", "akım", HS, X, sub="SEN_VH")
c("SEN_MOTOR_TEMP", "Motor Temperature", "SEN", "Sargı/mıknatıs sıcaklığı", "motor", "sıcaklık",
  HS, X, sub="SEN_VH")
c("SEN_ACT_POS", "Actuator Position Feedback", "SEN", "Elevon konum geri beslemesi",
  "yüzey konumu", "ölçülen konum", "takılı/devre dışı -> artık", I,
  ("simurg/sim/actuators.py::ActuatorState",), sub="SEN_VH")
c("SEN_BATT", "Battery State", "SEN", "Batarya SoC/güç ölçümü", "batarya", "SoC, güç", HS, P,
  ("simurg/power/energy_manager.py::EnergyManager",), sub="SEN_EN",
  note="Model durumu doğrudan okunur; ölçüm gürültüsü yok")
c("SEN_FC", "Fuel-Cell State", "SEN", "Yakıt hücresi gücü/H2 kalan", "yakıt hücresi", "güç, H2",
  HS, P, ("simurg/power/energy_manager.py::EnergyManager",), sub="SEN_EN")
c("SEN_SC", "Supercapacitor State", "SEN", "Süperkap SoC", "süperkap", "SoC", HS, P,
  ("simurg/power/energy_manager.py::EnergyManager",), sub="SEN_EN")
c("SEN_SOLAR", "Solar Input Estimate", "SEN", "Güneş girdisi kestirimi", "panel", "güç", HS, P,
  ("simurg/power/energy_manager.py::PowerSplit",), sub="SEN_EN", note="Girdi olarak verilir")
c("SEN_BUS_VI", "Bus Voltage/Current Monitor", "SEN", "DC bara gerilim/akım ve karşılanamayan güç",
  "bara", "yük, karşılanamayan güç", HS, P, ("simurg/power/energy_manager.py::PowerSplit",),
  sub="SEN_EN", note="Güç dengesi düzeyinde; gerilim modellenmez")
c("SEN_DRIVER", "Sensor Driver", "SEN", "Sensör okuma soyutlaması", "sensör modelleri",
  "ham ölçüm (SensorMeasurement)", HS, I, ("simurg/sim/sensors.py::SensorModel",), sub="SEN_PIPE")
c("SEN_COND", "Signal Conditioning", "SEN", "Ölçek, filtre, birim dönüşümü", "ham ölçüm",
  "koşullandırılmış ölçüm", HS, X, sub="SEN_PIPE")
c("SEN_PLAUS", "Plausibility Check", "SEN", "Sonluluk/aralık/akla yatkınlık denetimi",
  "zaman damgalı ölçüm", "geçerli ölçüm + bayrak", "geçersiz -> kullanılamaz", I,
  ("simurg/nav/providers.py::NavigationSystem", "simurg/sim/airdata.py::AirDataSystem"), sub="SEN_PIPE")
c("SEN_HEALTH", "Sensor Health Status", "SEN", "Sensör başına sağlık/kalite/dropout durumu",
  "denetlenmiş ölçüm", "sensör sağlık durumu", HS, I,
  ("simurg/core/types.py::SensorMeasurement",), sub="SEN_PIPE")

# ============================================================ MISSION COMPUTER
c("MC_MISSION_MGR", "Mission Manager", "MC", "Görev ilerleyişi, nominal mod isteği, iptal/tamamlanma",
  "durum, enerji rezervi, operatör komutu", "mod isteği (FSM'e), hedefler", "görev sonucu gerekçesi",
  I, ("simurg/sim/mission.py::MissionManager",), sub="MC_PLAN", proposal=True)
c("MC_TASK_PLANNER", "Task Planner", "MC", "Görev hedeflerini görevlere ayırma", "görev tanımı",
  "görev listesi", HS, X, sub="MC_PLAN", proposal=True)
c("MC_ROUTE_PLANNER", "Route Planner", "MC", "Görevlerden ara nokta rotası", "görevler, harita",
  "ara noktalar", HS, P, ("simurg/sim/scenario.py::MissionProfile",), sub="MC_PLAN", proposal=True,
  note="Rota senaryoda sabit tanımlanır; planlayıcı yok")
c("MC_SEARCH_PATTERN", "Search Pattern Generator", "MC", "Arama-tarama deseni (şerit/spiral)",
  "arama alanı", "ara noktalar", HS, X, sub="MC_PLAN", proposal=True)
c("MC_MISSION_DB", "Mission Database", "MC", "Görev, rota ve alan tanımlarının deposu",
  "yapılandırma", "görev profili", HS, P, ("simurg/sim/scenario.py::MissionProfile",),
  sub="MC_PLAN", proposal=True)
c("MC_RULES", "Mission Rules Engine", "MC", "Görev kuralları (yasak bölge, öncelik, süre)",
  "görev, durum", "kural ihlali/izin", HS, X, sub="MC_PLAN", proposal=True)
c("MC_RTA_IF", "RTA Proposal Interface", "MC", "Görev önerilerini tek tip Command olarak RTA'ya iletme",
  "planlayıcı çıktısı", "Command (öneri)", "n/a (durumsuz)", I,
  ("simurg/safety/rta.py::Command",), sub="MC_PLAN", proposal=True)
c("MC_HEALTH", "Mission Health Monitor", "MC", "Görev bilgisayarının kendi sağlığı", "görev süreçleri",
  "görev bilgisayarı sağlığı", HS, X, sub="MC_PLAN", proposal=True)
c("MC_PERCEPTION_MGR", "Perception Manager", "MC", "Algılama hattının yönetimi", "kamera/yük verisi",
  "algı olayları", HS, X, sub="MC_PERC", proposal=True)
c("MC_AI_RUNTIME", "AI Inference Runtime", "MC", "YZ modellerinin çalıştırılması (yalnızca öneri)",
  "algı verisi", "çıkarım sonuçları", HS, X, sub="MC_PERC", proposal=True)
c("MC_SCENE", "Object/Scene Understanding", "MC", "Termal anomali, duman, yapısal hasar sınıflandırma",
  "çıkarım", "sahne olayları", HS, X, sub="MC_PERC", proposal=True)
c("MC_TERRAIN", "Terrain Analysis", "MC", "Arazi eğimi, iniş uygunluğu", "yükseklik modeli",
  "uygun alanlar", HS, X, sub="MC_PERC", proposal=True)
c("MC_MAPPING", "Mapping", "MC", "Görev haritası/ortofoto", "algı + konum", "harita", HS, X,
  sub="MC_PERC", proposal=True)
c("MC_PAYLOAD_MGR", "Payload Manager", "MC", "Gözlem yükünün yönetimi (kamera/sensör bölmesi)",
  "görev", "yük durumu", HS, X, sub="MC_PERC", proposal=True,
  note="Yalnızca gözlem/haberleşme yükleri; yük bırakma kapsam dışı")
c("MC_SWARM_COORD", "Swarm Coordinator", "MC", "Sürü görev paylaşımının yönetimi", "komşu durumları",
  "görev ataması", HS, P, ("simurg/swarm/auction.py::allocate",), sub="MC_SWARM", proposal=True,
  note="Simülasyon motoruna bağlı değil")
c("MC_CBBA", "CBBA Task Allocator", "MC", "Zaman indirgemeli, enerji farkındalıklı görev dağıtımı",
  "ajanlar, görevler", "ajan başına rota", "n/a", P, ("simurg/swarm/auction.py::allocate",),
  sub="MC_SWARM", proposal=True, note="Merkezi-eşdeğer referans; dağıtık uzlaşı yok")
c("MC_MESH_COORD", "Mesh Coordination", "MC", "Sürü içi uzlaşı mesajları", "V2V mesajları",
  "uzlaşı tabloları", HS, X, sub="MC_SWARM", proposal=True)

# ============================================================ NAVIGATION
c("NAV_SRC_MGR", "Navigation Source Manager", "NAV", "Konum sağlayıcılarını toplama, kullanılamayanları ayırma",
  "sensör ölçümleri", "aday ölçümler, kullanılamayan kaynaklar", HS, I,
  ("simurg/nav/providers.py::NavigationSystem",), sub="NAV_PIPE")
c("NAV_TIME_ALIGN", "Measurement Time Alignment", "NAV", "Ölçümleri kestirim epokuna hizalama",
  "zaman damgalı ölçümler", "hizalı ölçümler", HS, X, sub="NAV_PIPE")
c("NAV_MEAS_VALID", "Measurement Validation", "NAV", "Geçerli/sonlu ölçüm seçimi",
  "aday ölçümler", "doğrulanmış ölçümler", HS, I, ("simurg/nav/providers.py::NavigationSystem",),
  sub="NAV_PIPE")
c("NAV_ESTIMATOR", "State Estimator", "NAV", "Konum füzyonu (ters kovaryans ağırlıklı)",
  "doğrulanmış ölçümler", "konum + kovaryans", HS, P, ("simurg/nav/integrity.py::fuse",),
  sub="NAV_PIPE", note="Yatay konum füzyonu; tam ESKF (tutum/sapma) planlanan")
c("NAV_SOLUTION", "Navigation Solution", "NAV", "Bütünlük bilgili çözüm nesnesi",
  "kestirim + bütünlük", "NavigationSolution", HS, I,
  ("simurg/core/types.py::NavigationSolution",), sub="NAV_PIPE")
c("NAV_INTEGRITY", "Integrity Monitor", "NAV", "Ki-kare tutarlılık testi", "kaynaklar + çözüm",
  "test istatistiği, eşik", HS, I, ("simurg/nav/integrity.py::IntegrityMonitor",), sub="NAV_PIPE")
c("NAV_PL", "Protection Level Calculator", "NAV", "PL = k_md · sqrt(λmax(P))", "kovaryans",
  "koruma seviyesi", HS, I, ("simurg/nav/integrity.py::IntegrityMonitor",), sub="NAV_PIPE")
c("NAV_FD", "Fault Detection", "NAV", "Tutarsızlık tespiti (T > eşik)", "test istatistiği",
  "arıza var/yok", HS, I, ("simurg/nav/integrity.py::IntegrityMonitor",), sub="NAV_PIPE")
c("NAV_FE", "Fault Exclusion", "NAV", "Leave-one-out ile hatalı kaynağı dışlama",
  "kaynak kümesi", "dışlanan kaynaklar", HS, I, ("simurg/nav/integrity.py::IntegrityMonitor",),
  sub="NAV_PIPE")
c("NAV_CONFIDENCE", "Navigation Confidence", "NAV", "PL ve bütünlükten güven değeri",
  "PL, bütünlük", "güven (0..1)", HS, I, ("simurg/nav/providers.py::NavigationSystem",), sub="NAV_PIPE")
c("NAV_SUPERVISOR", "Navigation Supervisor", "NAV",
  "Çıktı: konum, hız, güven, PL, aktif/dışlanan kaynak, bütünlük; olay üretimi",
  "çözüm + güven", "durum veriyolu + nav olayları", HS, P,
  ("simurg/sim/engine.py::SimulationEngine",), sub="NAV_PIPE",
  note="Olaylar motor içinde; tutum çıktısı kusursuz varsayım")
for sid, nm in (("GNSS", "GNSS Monitor"), ("VIO", "VIO Monitor"), ("TRN", "TRN Monitor"),
                ("MAGNAV", "MagNav Monitor")):
    c(f"NAV_MON_{sid}", nm, "NAV", f"{sid} kaynağına özgü sağlık izleme (sinyal kalitesi, sıçrama)",
      f"{sid} ölçümleri", "kaynak sağlığı", HS, X, sub="NAV_MON",
      note="Bugün tüm kaynaklar ortak FDE ile izlenir")
c("NAV_MON_INERTIAL", "Inertial Monitor", "NAV", "Ataletsel ilerletmenin yaşı/PL büyümesi",
  "ilerletme süresi", "ataletsel güven", HS, P, ("simurg/nav/providers.py::NavigationSystem",),
  sub="NAV_MON")

# ============================================================ GNC
c("G_MISSION", "Mission Guidance", "GNC", "Gelişmiş kontrolcü: ara noktaya rota + irtifa (öneri)",
  "durum, hedef", "Command önerisi", "n/a", I, ("simurg/control/guidance.py::MissionGuidance",),
  sub="GNC_G", proposal=True)
c("G_PATH", "Path Manager", "GNC", "Hedefe yol (bugün düz rota)", "ara nokta", "rota hatası",
  "n/a", P, ("simurg/control/guidance.py::MissionGuidance",), sub="GNC_G", proposal=True)
c("G_WAYPOINT", "Waypoint Manager", "GNC", "Ara nokta ilerleyişi ve hedef seçimi",
  "konum, ara noktalar", "aktif hedef", "n/a", I, ("simurg/sim/mission.py::MissionManager",),
  sub="GNC_G", proposal=True)
c("G_TRANSITION", "Transition Guidance", "GNC", "VTOL<->sabit kanat yunuslama programı ve iptal",
  "hız, yunuslama, irtifa, doyma", "TransitionStatus", "iptal gerekçesi", I,
  ("simurg/control/transition.py::TransitionCoordinator",), sub="GNC_G")
c("G_RETURN", "Return Guidance", "GNC", "Eve dönüş rotası (öneri)", "konum, ev", "Command önerisi",
  "n/a", I, ("simurg/control/guidance.py::MissionGuidance",), sub="GNC_G", proposal=True)
c("G_LOITER", "Loiter Guidance", "GNC", "Sabit yatışlı bekleme (öneri)", "durum", "Command önerisi",
  "n/a", I, ("simurg/control/guidance.py::MissionGuidance",), sub="GNC_G", proposal=True)
c("C_ATT", "Attitude Controller", "GNC", "Kuaterniyon tutum hatası -> moment isteği",
  "tutum hedefi, açısal hız", "moment isteği", "kontrol kaybı zamanlayıcısı", I,
  ("simurg/control/flight_controller.py::FlightController",), sub="GNC_C",
  note="Araştırma amaçlı PD; INDI planlanan")
c("C_VEL", "Velocity Controller", "GNC", "Hava hızı PI / dikey hız -> itki", "hız hatası, güç sınırı",
  "itki isteği", "n/a", P, ("simurg/control/flight_controller.py::FlightController",), sub="GNC_C")
c("C_POS", "Position Controller", "GNC", "Askıda yatay konum tutma -> eğim", "konum, hedef",
  "eğim açıları", "n/a", P, ("simurg/control/flight_controller.py::FlightController",), sub="GNC_C")
c("C_TRANS", "Transition Controller", "GNC", "Geçişte yunuslama programı + dikey itki yasası",
  "TransitionStatus", "tutum hedefi + itki", "n/a", I,
  ("simurg/sim/vehicle_control.py::VehicleController",), sub="GNC_C")
c("C_SAFETY", "Safety Controller", "GNC", "Basit, öngörülebilir güvenli komut (kanat düz, irtifa, geofence)",
  "durum, geofence", "güvenli Command", "n/a", I, ("simurg/control/guidance.py::SafetyController",),
  sub="GNC_C")

# ============================================================ RTA
c("RTA_VALIDATOR", "Command Validator / Sanitizer", "RTA", "Öneri tipi, sonluluk, fiziksel akla yatkınlık",
  "Command önerisi", "geçerli öneri ya da red", "red gerekçesi", I,
  ("simurg/safety/command_validator.py::CommandValidator",), sub="RTA_PATH")
c("RTA_PREDICTOR", "State Predictor", "RTA", "Öneri uygulanırsa ufuk sonundaki durum",
  "durum, öneri", "öngörülen durum", "n/a", I, ("simurg/safety/rta.py::KinematicPredictor",),
  sub="RTA_PATH")
c("RTA_ENVELOPE", "Safety Envelope Monitor", "RTA", "Mevcut durumu sert zarfla karşılaştırma",
  "durum", "mevcut ihlaller", "NaN -> gecersiz_durum", I, ("simurg/safety/rta.py::Envelope",),
  sub="RTA_PATH")
c("RTA_CONSTRAINT", "Constraint Evaluator", "RTA", "Tek tek kısıt denetimi (irtifa, hız, yatış, yunuslama, geofence)",
  "durum", "ihlal listesi + pay", "n/a", I, ("simurg/safety/rta.py::Envelope",), sub="RTA_PATH")
c("RTA_FUTURE", "Future State Checker", "RTA", "Öngörülen durumu yumuşak zarfla karşılaştırma",
  "öngörülen durum", "öngörülen ihlaller", "n/a", I, ("simurg/safety/rta.py::RuntimeAssurance",),
  sub="RTA_PATH")
c("RTA_DECISION", "Decision Logic", "RTA", "Kaynak seçimi kuralları (kilit, müdahale, geri dönüş)",
  "ihlaller, kilit, histerezis", "SafetyDecision", "kilitli/serbest", I,
  ("simurg/safety/rta.py::RuntimeAssurance",), sub="RTA_PATH")
c("RTA_SELECTOR", "RTA Command Selector", "RTA", "Nihai güvenlik kapısı: gelişmiş ya da güvenli komut",
  "öneri + güvenli komut + karar", "ValidatedCommand (mühürlü)", "n/a", I,
  ("simurg/safety/rta.py::ValidatedCommand",), sub="RTA_PATH")
c("RTA_LOGGER", "Intervention Logger", "RTA", "Müdahale/geri dönüş/kilit olaylarını yayınlama",
  "SafetyDecision", "RTA olayları", "n/a", I, ("simurg/sim/engine.py::SimulationEngine",),
  sub="RTA_SUPPORT")
c("RTA_REASON", "Reason Generator", "RTA", "Açıklanabilir gerekçe (öngörülen/mevcut ihlaller)",
  "ihlaller", "gerekçeler", "n/a", I, ("simurg/safety/rta.py::SafetyDecision",), sub="RTA_SUPPORT")
c("RTA_LATCH", "Latch Manager", "RTA", "Sert ihlalde uçuş sonuna dek güvenli kaynağa kilit",
  "sert ihlal", "kilit durumu", "kilitli", I, ("simurg/safety/rta.py::RuntimeAssurance",),
  sub="RTA_SUPPORT")
c("RTA_HYST", "Recovery Hysteresis", "RTA", "Gelişmiş kaynağa dönüş için ardışık güvenli çevrim",
  "zarf payı", "geri dönüş izni", "n/a", I, ("simurg/safety/rta.py::RuntimeAssurance",),
  sub="RTA_SUPPORT")
c("RTA_HEALTH", "RTA Runtime Health", "RTA", "RTA'nın kendi zamanlama/çalışma sağlığı",
  "çevrim zamanı", "RTA sağlığı", HS, X, sub="RTA_SUPPORT")

# ============================================================ LANES
for L, st in (("A", P), ("B", X)):
    note = ("Simülasyon tek şerit çalıştırır; işlevler bu şeritte, bölümleme/platform modellenmez"
            if L == "A" else "Farklı mimarili ikinci uygulama (planlanan)")
    code = ("simurg/sim/engine.py::SimulationEngine",) if L == "A" else ()
    for sid, nm, resp, hosts in (
            ("INPUT", "Input Manager", "Şeride girdi toplama ve tazelik denetimi", "veriyolu"),
            ("EST", "State Estimation", "Şerit içi durum kestirimi (NAVIGATION işlevlerini barındırır)", "NAV"),
            ("GUID", "Guidance", "Şerit içi güdüm (GNC/GUIDANCE işlevlerini barındırır)", "GNC_G"),
            ("CTRL", "Control", "Şerit içi kontrol (GNC/CONTROL + ALLOCATION barındırır)", "GNC_C"),
            ("SAFETY", "Safety Monitor", "Şerit içi RTA/güvenlik çekirdeği (güvenlik kapısı)", "RTA"),
            ("OUT", "Output Proposal", "Şeridin eyleyici komut önerisi", "ALLOC")):
        c(f"L{L}_{sid}", nm, f"LANE{L}", resp, "şerit içi", "şerit çıktısı",
          "şerit: NOMINAL/DEGRADED/ISOLATED/FAILED", st, code, note=note)
c("LC_SENSORS", "Independent Sensor Observation", "LANEC", "Bağımsız IMU ile hareket gözlemi",
  "IMU C", "bağımsız durum", HS, X)
c("LC_CROSS", "Cross-Lane Output Monitor", "LANEC", "A/B çıktılarını bağımsız durumla karşılaştırma",
  "şerit çıktıları", "uyuşmazlık", HS, X)
c("LC_CMD_MON", "Command Monitor", "LANEC", "Komutların zarf/oran sınırları içinde olduğunu denetleme",
  "şerit çıktıları", "komut ihlali", HS, X)
c("LC_WATCHDOG", "Watchdog", "LANEC", "Şerit yaşam sinyali zaman aşımı", "kalp atışı", "şerit canlı mı",
  HS, X)
c("LC_INTEGRITY", "Integrity Checking", "LANEC", "Çerçeve CRC/sıra/tazelik denetimi",
  "şerit mesajları", "bütünlük", HS, X)
c("LANE_COMPARATOR", "Lane Comparator", "LANEM", "Şerit çıktılarının karşılaştırılması",
  "A/B/C çıktıları", "fark vektörü", "n/a", P, ("simurg/fdir/monitor.py::TripleLaneVoter",),
  note="Oylayıcı mevcut; simülasyona bağlı değil")
c("LANE_VOTER", "Lane Voter", "LANEM", "Orta değer seçimi / ikili modda ortalama",
  "şerit çıktıları, yalıtım", "oylanmış komut", "n/a", P, ("simurg/fdir/monitor.py::TripleLaneVoter",))
c("LANE_XDATA", "Cross-Lane Data Monitor", "LANEM", "Şerit girdilerinin tutarlılığı",
  "şerit girdileri", "girdi uyuşmazlığı", HS, X)
c("LANE_HEARTBEAT", "Heartbeat Monitor", "LANEM", "Şerit kalp atışları", "şeritler", "canlılık", HS, X)
c("LANE_TIMING", "Timing Monitor", "LANEM", "Şerit çevrim süreleri ve son tarih ihlali",
  "çizelge", "zamanlama ihlali", HS, X)
c("LANE_DIVERGENCE", "Divergence Detector", "LANEM", "Kalıcı ayrışma (ardışık uyuşmazlık sayacı)",
  "fark vektörü", "ayrışan şerit", HS, P, ("simurg/fdir/monitor.py::TripleLaneVoter",))
c("LANE_ISOLATION", "Lane Isolation Manager", "LANEM", "Şeridi DEGRADED/ISOLATED/FAILED yapma",
  "ayrışma, zamanlama, kalp atışı", "şerit durumu", "NOMINAL/DEGRADED/ISOLATED/FAILED", P,
  ("simurg/fdir/monitor.py::TripleLaneVoter",), note="Yalnızca ISOLATED; DEGRADED/FAILED planlanan")

# ============================================================ ALLOCATION
c("AL_EFFECTIVENESS", "Effectiveness Provider B(V, σ)", "ALLOC", "Rejime bağlı etkinlik matrisi",
  "hız, σ, itki ölçeği, yapılandırma", "ControlRegime", "n/a", I,
  ("simurg/control/effectiveness.py::ScheduledEffectiveness",))
c("AL_ALLOCATOR", "Control Mixer / Allocator", "ALLOC", "Sağlık farkındalıklı RPI dağıtımı",
  "kuvvet/moment isteği, sağlık, rejim", "eyleyici komutu, doyma", "doyma oranı", I,
  ("simurg/control/allocation.py::ScheduledAllocator",))
c("AL_HOVER_MARGIN", "Control Authority Estimator", "ALLOC", "Askı marjı (itki/ağırlık) hesabı",
  "sağlık vektörü", "hover marjı", "bilinmeyen eyleyici = çalışmıyor (havada)", I,
  ("simurg/sim/health.py::HealthSupervisor",))
c("AL_LIMITER", "Command Limiter", "ALLOC", "Eyleyici sınırlarına kırpma", "dağıtım çıktısı",
  "sınırlı komut", "n/a", I, ("simurg/sim/actuators.py::ActuatorModel",))
c("AL_CMD_MGR", "Actuator Command Manager", "ALLOC", "Komutun zaman damgasıyla eyleyicilere dağıtımı",
  "oylanmış komut", "ActuatorCommand", "n/a", P, ("simurg/sim/actuators.py::ActuatorCommand",))
c("AL_HEALTH_GATE", "Actuator Health Gate", "ALLOC", "FAILED eyleyiciyi dağıtım dışı bırakma (komut 0)",
  "komut, sağlık", "kapılı komut", "n/a", I, ("simurg/control/allocation.py::ControlAllocator",))

# ============================================================ ACTUATORS
for m in ("M1U", "M2U", "M3U", "M4U", "M1L", "M2L", "M3L", "M4L"):
    c(f"ACT_{m}", f"Motor {m}", "ACT", "Motor + pervane itkisi (soyutlama: gecikme, tepki, doyma)",
      "normalize itki komutu", "itki, devir", "NOMINAL/DEGRADED/STUCK/OFFLINE", I,
      ("simurg/sim/actuators.py::ActuatorModel",), sub="ACT_M")
for e in ("E1U", "E2U", "E1L", "E2L"):
    c(f"ACT_{e}", f"Elevon {e}", "ACT", "Kontrol yüzeyi (soyutlama)", "normalize sapma",
      "sapma, konum geri beslemesi", "NOMINAL/DEGRADED/STUCK/OFFLINE", I,
      ("simurg/sim/actuators.py::ActuatorModel",), sub="ACT_E")

# ============================================================ FDIR
c("FDIR_SUP", "FDIR Supervisor", "FDIR", "Alan FDIR'lerini çalıştırma ve rapor değişimlerini yayınlama",
  "alan raporları", "ComponentHealth olayları", HS, P, ("simurg/sim/health.py::HealthSupervisor",),
  note="Motor/yüzey için tam; diğer alanlar motor içinde dağınık")
c("FDIR_SENSOR", "Sensor FDIR", "FDIR", "Sensör dropout/geçersizlik tespiti ve geri dönüş",
  "sensör sağlığı", "sensör alanı sağlığı", HS, P, ("simurg/sim/airdata.py::AirDataSystem",),
  sub="FDIR_DOM")
c("FDIR_MOTOR", "Motor FDIR", "FDIR", "CUSUM + verim kestirimi ile motor/pervane arızası",
  "beklenen/ölçülen devir", "motor sağlığı", "NOMINAL/DEGRADED/FAILED/UNKNOWN", I,
  ("simurg/fdir/monitor.py::MotorHealthMonitor",), sub="FDIR_DOM")
c("FDIR_ACTUATOR", "Actuator FDIR", "FDIR", "Yüzey komut-konum artığı (takılı/devre dışı)",
  "beklenen/ölçülen konum", "yüzey sağlığı", "NOMINAL/FAILED", P,
  ("simurg/fdir/monitor.py::SurfaceMonitor",), sub="FDIR_DOM", note="Yüzey verim kaybı gözlenemez")
c("FDIR_NAV", "Navigation FDIR", "FDIR", "Kaynak dışlama, bütünlük kaybı", "nav çözümü",
  "nav alanı sağlığı", HS, I, ("simurg/nav/integrity.py::IntegrityMonitor",), sub="FDIR_DOM")
c("FDIR_POWER", "Power FDIR", "FDIR", "Güç açığı, kaynak bozunumu, rezerv uyarısı",
  "enerji durumu", "güç alanı sağlığı", HS, P, ("simurg/power/reserve.py::ReserveMonitor",),
  sub="FDIR_DOM")
c("FDIR_COMM", "Communication FDIR", "FDIR", "C2 kaybı ve süresi", "bağlantı durumu",
  "haberleşme alanı sağlığı", HS, P, ("simurg/sim/link.py::LinkModel",), sub="FDIR_DOM")
c("FDIR_LANE", "Computer/Lane FDIR", "FDIR", "Şerit uyuşmazlığı ve yalıtımı", "şerit durumları",
  "şerit sağlığı", "NOMINAL/DEGRADED/ISOLATED/FAILED", P, ("simurg/fdir/monitor.py::TripleLaneVoter",),
  sub="FDIR_DOM", note="Araç sağlık modelinde 'modellenmedi' olarak işaretli")
c("FDIR_DETECT", "Detection", "FDIR", "Artık/eşik/istatistik ile anomali tespiti", "alan verisi",
  "tespit", "n/a", I, ("simurg/fdir/monitor.py::MotorHealthMonitor",), sub="FDIR_PIPE")
c("FDIR_ISOLATE", "Isolation", "FDIR", "Arızalı bileşenin belirlenmesi", "tespitler",
  "arızalı bileşen", "n/a", I, ("simurg/fdir/monitor.py::MotorHealthMonitor",), sub="FDIR_PIPE")
c("FDIR_CLASSIFY", "Classification", "FDIR", "DEGRADED / FAILED / UNKNOWN sınıflandırması",
  "yalıtılmış arıza", "sağlık durumu", HS, I, ("simurg/core/types.py::HealthState",), sub="FDIR_PIPE")
c("FDIR_SCORE", "Health Score", "FDIR", "0..1 sağlık puanı + güven", "sınıf, kestirim",
  "ComponentHealth", HS, I, ("simurg/core/types.py::ComponentHealth",), sub="FDIR_PIPE")
c("FDIR_RECOVERY", "Recovery Recommendation", "FDIR", "Yeniden yapılandırma (sağlık vektörü) ve acil durum girdisi",
  "sağlık", "dağıtım sağlığı, hover marjı", "n/a", P,
  ("simurg/sim/engine.py::SimulationEngine",), sub="FDIR_PIPE",
  note="Öneri açık bir nesne değil; sağlık vektörü + acil durum bağlamı")
c("FDIR_VHM", "Vehicle Health Model", "FDIR", "Alan sağlıklarını birleştirip araç durumunu üretme",
  "alan raporları", "VehicleHealth", HS, I, ("simurg/fdir/vehicle_health.py::VehicleHealthModel",))

# ============================================================ ENERGY
c("EN_FC_MODEL", "Hydrogen Fuel Cell Model", "EN", "PEM gücü, eğim sınırı, verim, H2 tüketimi",
  "hedef güç", "FC gücü", "bozunum ölçeği", I, ("simurg/power/energy_manager.py::fc_efficiency",),
  sub="EN_SRC")
c("EN_BATT_MODEL", "Battery Model", "EN", "SoC, deşarj/şarj sınırı, verim", "güç", "SoC",
  "kapasite/deşarj ölçeği", I, ("simurg/power/energy_manager.py::EnergyManager",), sub="EN_SRC")
c("EN_SC_MODEL", "Supercapacitor Model", "EN", "Hızlı tepe güç tamponu", "güç", "SoC",
  "güç ölçeği", I, ("simurg/power/energy_manager.py::EnergyManager",), sub="EN_SRC")
c("EN_SOLAR_MODEL", "Solar Model", "EN", "Güneş katkısı", "güneş girdisi", "güç", "n/a", P,
  ("simurg/power/energy_manager.py::EnergyManager",), sub="EN_SRC",
  note="Simülasyon motorunda 0 W (girdi olarak destekli)")
c("EN_SRC_MON", "Energy Source Monitor", "EN", "Kaynak durumlarının özeti", "kaynak modelleri",
  "EnergyState", HS, I, ("simurg/core/types.py::EnergyState",), sub="EN_MGMT")
c("EN_AVAIL", "Power Availability Estimator", "EN", "Kaynak başına anlık güç sınırları",
  "SoC, ölçekler", "kullanılabilir güç", "n/a", P, ("simurg/power/energy_manager.py::EnergyManager",),
  sub="EN_MGMT")
c("EN_DEMAND", "Power Demand Predictor", "EN", "İtki + aviyonik elektrik yükü", "itki, hız",
  "anlık talep", "n/a", P, ("simurg/sim/propulsion.py::PropulsionModel",), sub="EN_MGMT",
  note="Anlık talep; ileri tahmin planlanan")
c("EN_ARBITRATION", "Power Arbitration", "EN", "Frekans ayrıştırmalı kaynak paylaşımı",
  "talep, kullanılabilir güç", "kaynak güçleri, karşılanamayan güç", "n/a", I,
  ("simurg/power/energy_manager.py::EnergyManager",), sub="EN_MGMT")
c("EN_MANAGER", "Energy Manager", "EN", "Hibrit enerji yönetimi ve durum güncelleme",
  "talep", "PowerSplit, EnergyState", HS, I, ("simurg/power/energy_manager.py::EnergyManager",),
  sub="EN_MGMT")
c("EN_RESERVE", "Reserve Estimator", "EN", "Eve dönüş enerji ihtiyacı ve uyarı histerezisi",
  "kullanılabilir enerji, mesafe", "rezerv değerlendirmesi", "bilinmeyen enerji -> uyarı", I,
  ("simurg/power/reserve.py::ReserveMonitor",), sub="EN_MGMT")
c("EN_THERMAL", "Thermal State", "EN", "Batarya/FC sıcaklık modeli", "güç", "sıcaklık", HS, X,
  sub="EN_SUPV")
c("EN_SRC_HEALTH", "Source Health", "EN", "Kaynak bozunum özeti", "ölçekler", "kaynak sağlığı",
  HS, I, ("simurg/power/energy_manager.py::EnergyManager",), sub="EN_SUPV")
c("EN_BUS_HEALTH", "Bus Health", "EN", "Karşılanamayan güç ve itki güç faktörü", "PowerSplit",
  "bara sağlığı", HS, P, ("simurg/sim/engine.py::SimulationEngine",), sub="EN_SUPV")
c("EN_FAULT_DET", "Energy Fault Detection", "EN", "Kalıcı güç açığı (0,5 s) ve bozunum tespiti",
  "bara + kaynak sağlığı", "enerji arızası", HS, P,
  ("simurg/fdir/vehicle_health.py::VehicleHealthModel",), sub="EN_SUPV")
c("EN_EMERGENCY_POLICY", "Emergency Energy Policy", "EN", "Acil modlarda rezervin kullanıma açılması",
  "mod", "rezerv kilidi", "n/a", I, ("simurg/power/energy_manager.py::EnergyManager",), sub="EN_SUPV")

# ============================================================ COMMUNICATION
for cid, nm, resp, st, code in (
        ("GROUND", "Ground Link Interface", "Yer istasyonu bağlantısı (soyutlama)", P,
         ("simurg/sim/link.py::LinkModel",)),
        ("MESH", "Mesh Link Interface", "Sürü mesh bağlantısı", X, ()),
        ("V2V", "Vehicle-to-Vehicle Interface", "Araçlar arası mesajlaşma", X, ()),
        ("TLM_ROUTER", "Telemetry Router", "Telemetrinin bağlantılara yönlendirilmesi", X, ()),
        ("CMD_ROUTER", "Command Router", "Doğrulanmış yer komutlarının hedef alt sisteme yönlendirilmesi", X, ()),
        ("MSG_VALID", "Message Validation", "Şema/aralık denetimi", X, ()),
        ("AUTH", "Authentication (abstraction)", "Kimlik doğrulama soyutlaması", X, ()),
        ("SEQ", "Sequence Checker", "Sıra numarası / tekrar denetimi", X, ()),
        ("LINK_QUALITY", "Link Quality Monitor", "Gecikme/kayıp ölçümü", X, ()),
        ("HEARTBEAT", "Heartbeat", "Bağlantı yaşam sinyali ve kesinti süresi", P,
         ("simurg/sim/link.py::LinkModel",)),
        ("FAILOVER", "Link Failover Manager", "Yedek bağlantıya geçiş", X, ()),
        ("HEALTH", "Communication Health", "Bağlantı var/yok ve kesinti süresi", P,
         ("simurg/sim/link.py::LinkModel",))):
    c(f"CO_{cid}", nm, "COMM", resp, "mesajlar", "mesajlar / durum", HS, st, code)

# ============================================================ MODE & CONTINGENCY
c("MD_FSM", "Flight Mode Machine", "MODE", "Yalnızca tablodaki geçişleri kabul (13 mod); güvenlik kapısı",
  "mod istekleri, bağlam", "aktif mod, TransitionRecord", "n/a", I,
  ("simurg/modes/flight_modes.py::FlightModeMachine",))
c("MD_TABLE", "Transition Table", "MODE", "Geçiş + koruma koşulları (tek kaynak)", "-",
  "izinli geçişler", "n/a", I, ("simurg/modes/flight_modes.py::TRANSITIONS",))
c("MD_CONTINGENCY", "Contingency Manager", "MODE", "Sistem çapı arızada önerilen güvenli mod",
  "nav, enerji, araç sağlığı, kontrol otoritesi, haberleşme, RTA", "ContingencyDecision", "n/a", I,
  ("simurg/modes/flight_modes.py::ContingencyManager",))
c("MD_RULES", "Contingency Rule Table", "MODE", "Öncelikli kurallar (docs/08 §3 ile eşleşir)", "-",
  "kurallar", "n/a", I, ("simurg/modes/flight_modes.py::CONTINGENCY_RULES",))

# ============================================================ PREFLIGHT
c("PRE_SUPERVISOR", "Preflight Supervisor", "PRE", "8 kontrolün tamamı geçmeden ARMED yok",
  "kontrol sonuçları", "PreflightReport, preflight_ok", "geçti/kaldı", I,
  ("simurg/sim/preflight.py::PreflightSupervisor",))
for pid, nm in (("CONFIG", "Configuration Check"), ("SENSOR", "Sensor Health Check"),
                ("NAV", "Navigation Check"), ("ENERGY", "Energy Check"),
                ("CONTROL", "Control Availability Check"), ("COMM", "Communication Check"),
                ("MISSION", "Mission Validation"), ("SAFETY", "Safety Configuration Check")):
    c(f"PF_{pid}", nm, "PRE", f"Uçuş öncesi: {nm}", "ilgili alt sistem durumu", "PreflightCheck",
      "geçti/kaldı + gerekçe", I, ("simurg/sim/preflight.py::PreflightSupervisor",))

# ============================================================ SYSTEM SUPERVISOR
c("SUP_SYSTEM", "System Supervisor", "SUP", "Üst seviye durum: NORMAL/DEGRADED/CONTINGENCY/EMERGENCY (eyleyici sürmez)",
  "mod, araç sağlığı, nav, enerji, RTA, haberleşme", "SystemAssessment", "sistem durumu", I,
  ("simurg/sim/supervisor.py::SystemSupervisor",))

# ============================================================ DATA BUS
c("BUS_STATE", "State Bus", "BUS", "Durum dağıtımı (konum, hız, tutum, enerji, mod)", "kestirim",
  "VehicleState", "n/a", P, ("simurg/core/types.py::VehicleState",),
  note="Mantıksal; süreç içi nesne geçişi")
c("BUS_EVENT", "Event Bus", "BUS", "Senkron, sıralı olay yayını", "olaylar", "abonelere olaylar", "n/a",
  I, ("simurg/core/events.py::EventBus",))
c("BUS_HEALTH", "Health Bus", "BUS", "Sağlık raporlarının dağıtımı", "FDIR", "ComponentHealth / VehicleHealth",
  "n/a", P, ("simurg/core/types.py::ComponentHealth",))
c("BUS_COMMAND", "Command Bus", "BUS", "Doğrulanmış komutların kontrol katmanına taşınması",
  "ValidatedCommand", "kontrol girdisi", "n/a", P, ("simurg/sim/vehicle_control.py::ControlInputs",))
c("BUS_TELEMETRY", "Telemetry Bus", "BUS", "Telemetri ve özet durum", "alt sistemler",
  "telemetri", "n/a", P, ("simurg/sim/recorder.py::SimulationRecorder",))

# ============================================================ TIME
c("TM_SIM_CLOCK", "Simulation Clock", "TIME", "Monoton simülasyon zamanı (sabit adım)", "-", "t",
  "monotonluk testli", I, ("simurg/sim/engine.py::SimulationEngine",))
c("TM_SYSTEM_TIME", "System Time", "TIME", "Araç sistem saati", "saat kaynağı", "sistem zamanı", HS, X)
c("TM_SENSOR_TS", "Sensor Timestamp Manager", "TIME", "Ölçümlere zaman damgası", "ölçümler",
  "zaman damgalı ölçümler", "n/a", P, ("simurg/core/types.py::SensorMeasurement",))
c("TM_CONSISTENCY", "Clock Consistency Monitor", "TIME", "Şerit/sensör saat tutarlılığı",
  "zaman damgaları", "saat kayması", HS, X)
c("TM_SCHED", "Scheduling Monitor", "TIME", "Sabit adım sırası ve son tarihler", "çizelge",
  "çizelge ihlali", "n/a", P, ("simurg/sim/engine.py::TICK_ORDER",), note="Sıra sabit ve testli; süre izleme yok")

# ============================================================ CONFIGURATION
c("CFG_MANAGER", "Configuration Manager", "CFG", "Değişmez (frozen) yapılandırma nesnelerinin sağlanması",
  "senaryo", "yapılandırmalar", "geçersiz -> ConfigurationError", P,
  ("simurg/core/config.py::VehicleConfig",), note="Dağıtık dataclass'lar; merkezi yönetici yok")
c("CFG_VEHICLE", "Vehicle Configuration", "CFG", "Kütle, atalet, eyleyiciler", "-", "VehicleConfig",
  "n/a", I, ("simurg/core/config.py::VehicleConfig",))
c("CFG_MISSION", "Mission Configuration", "CFG", "Görev profili", "-", "MissionProfile", "n/a", I,
  ("simurg/sim/scenario.py::MissionProfile",))
c("CFG_SAFETY", "Safety Configuration", "CFG", "Güvenlik eşikleri (uçuşta değiştirilemez)", "-",
  "SafetyConfig", "n/a", I, ("simurg/core/config.py::SafetyConfig",))
c("CFG_NAV", "Navigation Configuration", "CFG", "Bütünlük olasılıkları, alarm limiti", "-",
  "IntegrityMonitor parametreleri", "n/a", P, ("simurg/nav/integrity.py::IntegrityMonitor",),
  note="Değişebilir dataclass")
c("CFG_ENERGY", "Energy Configuration", "CFG", "Kaynak kapasite/sınırları", "-", "PowerConfig", "n/a",
  P, ("simurg/power/energy_manager.py::PowerConfig",), note="Değişebilir dataclass")
c("CFG_SIM", "Simulation Configuration", "CFG", "Adım, integratör, kayıt periyodu", "-",
  "SimulationConfig", "n/a", I, ("simurg/core/config.py::SimulationConfig",))

# ============================================================ FLIGHT DATA RECORDER
c("FDR_STATE", "State Recorder", "FDR", "Periyodik anlık görüntüler", "durum", "snapshots", "n/a", I,
  ("simurg/sim/recorder.py::SimulationRecorder",))
c("FDR_EVENT", "Event Recorder", "FDR", "Kayıpsız olay kaydı", "olay yolu", "events", "n/a", I,
  ("simurg/sim/recorder.py::SimulationRecorder",))
for fid, nm, ev in (("HEALTH", "Health Recorder", "fdir_* / vehicle_health_changed"),
                    ("RTA", "RTA Recorder", "rta_*"), ("MODE", "Mode Recorder", "mode_* / contingency"),
                    ("NAV", "Navigation Recorder", "nav_*")):
    c(f"FDR_{fid}", nm, "FDR", f"Olay türü görünümü: {ev}", "olay kaydı", "kategori geçmişi", "n/a",
      I, ("simurg/sim/replay.py::ReplaySession",))
c("FDR_ENERGY", "Energy Recorder", "FDR", "Enerji uyarıları + anlık görüntüde SoC", "olay + durum",
  "enerji geçmişi", "n/a", P, ("simurg/sim/replay.py::ReplaySession",),
  note="Sürekli güç kanalı kaydedilmez")
c("FDR_REPLAY_IF", "Replay Interface", "FDR", "Sürümlü JSON şeması ile kayıt dışa/içe aktarma",
  "kayıt", "simurg.sim-log v1", "bilinmeyen şema reddedilir", I, ("simurg/sim/recorder.py::load_log",))
c("FDR_DIAG", "Diagnostics", "FDR", "Kararların açıklanması (neden RETURN, neden RTA ...)",
  "kayıt", "explain()", "n/a", I, ("simurg/sim/replay.py::ReplaySession",))
c("FDR_POSTFLIGHT", "Post-flight Analysis", "FDR", "Standart metrikler ve görev sonucu gerekçesi",
  "kayıt", "SimulationMetrics", "n/a", I, ("simurg/sim/metrics.py::compute_metrics",))

# ============================================================ DIGITAL TWIN
for did, nm, resp, st, code in (
        ("VEHICLE", "Vehicle Model", "Araç yapılandırması + parametreler", I, ("simurg/core/config.py::VehicleConfig",)),
        ("6DOF", "6-DOF Dynamics", "Rijit cisim + RK4/Euler", I, ("simurg/sim/dynamics.py::RigidBodyDynamics",)),
        ("AERO", "Aerodynamic Model", "Analitik/tablo aero (sentetik katsayı)", I, ("simurg/aero/model.py::AnalyticAeroModel",)),
        ("PROP", "Propulsion Model", "İtki düşümü, pervane akımı, güç", I, ("simurg/sim/propulsion.py::PropulsionModel",)),
        ("ACTUATOR", "Actuator Model", "Gecikme, tepki, doyma, arıza modları", I, ("simurg/sim/actuators.py::ActuatorModel",)),
        ("SENSOR", "Sensor Model", "Gürültü, bias, dropout", I, ("simurg/sim/sensors.py::SensorModel",)),
        ("ENV", "Environment Model", "Rüzgâr, türbülans, yoğunluk", I, ("simurg/sim/environment.py::ConstantEnvironment",)),
        ("ENERGY", "Energy Model", "Kaynak durumları (bitki modeli olarak)", I, ("simurg/power/energy_manager.py::EnergyManager",)),
        ("FAULT", "Fault Injection", "Zaman tabanlı arıza enjeksiyonu", I, ("simurg/sim/faults.py::FaultInjector",)),
        ("SCENARIO", "Scenario Engine", "Senaryo kütüphanesi + beklentiler", I, ("simurg/sim/scenarios.py::SCENARIOS",)),
        ("ENGINE", "Simulation Engine", "14 adımlı deterministik orkestrasyon", I, ("simurg/sim/engine.py::SimulationEngine",)),
        ("MC", "Monte Carlo Runner", "Tohumla yeniden üretilebilir kampanyalar", I, ("simurg/sim/montecarlo.py::MonteCarloRunner",)),
        ("REPLAY", "Replay Engine", "Zaman çizelgesi ve karar analizi", I, ("simurg/sim/replay.py::ReplaySession",)),
        ("METRICS", "Metrics Engine", "Standart metrikler", I, ("simurg/sim/metrics.py::compute_metrics",))):
    c(f"DT_{did}", nm, "DT", resp, "senaryo/yapılandırma", "simülasyon çıktısı", "n/a", st, code)

# ============================================================ GROUND CONTROL STATION
for gid, nm, st, code in (
        ("OVERVIEW", "Vehicle Overview", X, ()), ("MAP", "Map", X, ()),
        ("MISSION_PLANNER", "Mission Planner", X, ()), ("HEALTH", "Health Panel", X, ()),
        ("NAV", "Navigation Integrity Panel", X, ()), ("ENERGY", "Energy Panel", X, ()),
        ("RTA", "RTA Intervention Panel", X, ()), ("ALERTS", "Alert Manager", X, ()),
        ("FLEET", "Fleet/Swarm View", X, ()),
        ("REPLAY", "Simulation Replay", P, ("simurg/sim/__main__.py::main",)),
        ("LOGS", "Log Viewer", P, ("simurg/sim/__main__.py::main",))):
    c(f"GCS_{gid}", nm, "GCS", f"Operatör arayüzü: {nm}", "telemetri / kayıt", "operatör görünümü / komut",
      "n/a", st, code, note="CLI (python -m simurg.sim replay)" if code else "")

COMPONENTS: tuple[Component, ...] = tuple(_C)

# ============================================================ EDGES
_E: list[Edge] = []


def e(src: str, dst: str, label: str = "", kind=D) -> None:
    _E.append(Edge(src, dst, label, kind))


# --- algı zinciri (soldan sağa)
for grp in ("SEN_INS", "SEN_AIR", "SEN_POS", "SEN_VH", "SEN_EN"):
    e(grp, "SEN_DRIVER")
e("SEN_DRIVER", "SEN_COND")
e("SEN_COND", "SEN_ACCEL_PROC")
e("SEN_COND", "SEN_GYRO_PROC")
e("SEN_ACCEL_PROC", "SEN_BIAS_EST")
e("SEN_GYRO_PROC", "SEN_BIAS_EST")
e("SEN_ACCEL_PROC", "SEN_VIB_MON")
e("SEN_COND", "SEN_PRESS_VALID")
e("SEN_COND", "TM_SENSOR_TS")
e("SEN_BIAS_EST", "TM_SENSOR_TS")
e("SEN_PRESS_VALID", "TM_SENSOR_TS")
e("TM_SENSOR_TS", "SEN_PLAUS")
e("SEN_PLAUS", "SEN_HEALTH")
e("SEN_VIB_MON", "SEN_HEALTH", "titreşim", S)
e("SEN_HEALTH", "NAV_SRC_MGR", "füzyon girdisi")
e("SEN_HEALTH", "FDIR_SENSOR", "sensör sağlığı", S)
e("SEN_HEALTH", "FDIR_MOTOR", "devir/akım", S)
e("SEN_HEALTH", "FDIR_ACTUATOR", "yüzey konumu", S)
e("SEN_HEALTH", "EN_SRC_MON", "enerji ölçümleri")
e("SEN_HEALTH", "LC_SENSORS", "IMU C")
# --- navigasyon hattı
e("NAV_SRC_MGR", "NAV_TIME_ALIGN")
e("NAV_TIME_ALIGN", "NAV_MEAS_VALID")
e("NAV_MEAS_VALID", "NAV_ESTIMATOR")
e("NAV_ESTIMATOR", "NAV_SOLUTION")
e("NAV_SOLUTION", "NAV_INTEGRITY")
e("NAV_INTEGRITY", "NAV_PL")
e("NAV_PL", "NAV_FD")
e("NAV_FD", "NAV_FE")
e("NAV_FE", "NAV_CONFIDENCE")
e("NAV_CONFIDENCE", "NAV_SUPERVISOR")
e("NAV_FE", "NAV_SRC_MGR", "dışlanan kaynaklar", S)
for sid in ("GNSS", "VIO", "TRN", "MAGNAV"):
    e(f"SEN_{sid}", f"NAV_MON_{sid}")
    e(f"NAV_MON_{sid}", "NAV_FD", "kaynak sağlığı", S)
e("SEN_INERTIAL_PROP", "NAV_MON_INERTIAL")
e("NAV_MON_INERTIAL", "NAV_FD", "ataletsel güven", S)
e("SEN_BIAS_EST", "SEN_INERTIAL_PROP", "IMU")
e("NAV_SUPERVISOR", "BUS_STATE", "konum/hız/tutum/güven/PL")
e("NAV_SUPERVISOR", "FDIR_NAV", "bütünlük", S)
# --- veri yolu dağıtımı
e("EN_MANAGER", "BUS_STATE", "EnergyState")
e("MD_FSM", "BUS_STATE", "aktif mod")
e("BUS_STATE", "LA_INPUT")
e("BUS_STATE", "LB_INPUT")
e("BUS_STATE", "GNC_G", "durum")
e("BUS_STATE", "GNC_C", "durum")
e("BUS_STATE", "RTA_PREDICTOR")
e("BUS_STATE", "RTA_ENVELOPE")
e("BUS_STATE", "MC_MISSION_MGR", "durum")
e("BUS_STATE", "EN_DEMAND", "uçuş durumu")
# --- görev bilgisayarı (öneri katmanı)
e("MC_PERCEPTION_MGR", "MC_AI_RUNTIME")
e("MC_AI_RUNTIME", "MC_SCENE")
e("MC_SCENE", "MC_MAPPING")
e("MC_TERRAIN", "MC_MAPPING")
e("MC_MAPPING", "MC_TASK_PLANNER")
e("MC_PAYLOAD_MGR", "MC_PERCEPTION_MGR")
e("MC_MISSION_DB", "MC_MISSION_MGR")
e("MC_RULES", "MC_MISSION_MGR", "kural", S)
e("MC_MISSION_MGR", "MC_TASK_PLANNER")
e("MC_TASK_PLANNER", "MC_SEARCH_PATTERN")
e("MC_SEARCH_PATTERN", "MC_ROUTE_PLANNER")
e("MC_TASK_PLANNER", "MC_ROUTE_PLANNER")
e("MC_SWARM_COORD", "MC_CBBA")
e("MC_CBBA", "MC_TASK_PLANNER", "atanan görevler")
e("MC_MESH_COORD", "MC_SWARM_COORD")
e("MC_ROUTE_PLANNER", "G_WAYPOINT", "ara noktalar", CMD)
e("MC_ROUTE_PLANNER", "MC_RTA_IF", "hedef", CMD)
e("MC_RTA_IF", "RTA_VALIDATOR", "öneri", CMD)
e("MC_MISSION_MGR", "MD_FSM", "nominal mod isteği", CMD)
e("MC_HEALTH", "SUP_SYSTEM", "görev bilg. sağlığı", S)
e("MC_MISSION_MGR", "BUS_TELEMETRY", "görev durumu")
e("MC_ROUTE_PLANNER", "EN_RESERVE", "rota mesafesi")
e("EN_RESERVE", "MC_MISSION_MGR", "rezerv kısıtı", S)
e("MC_MESH_COORD", "CO_MESH", "uzlaşı mesajları")
e("CO_V2V", "MC_MESH_COORD", "komşu durumları")
# --- güdüm (öneriler RTA'ya)
e("G_WAYPOINT", "G_PATH", "aktif hedef", CMD)
e("G_PATH", "G_MISSION", "rota", CMD)
e("G_MISSION", "RTA_VALIDATOR", "öneri", CMD)
e("G_RETURN", "RTA_VALIDATOR", "öneri", CMD)
e("G_LOITER", "RTA_VALIDATOR", "öneri", CMD)
e("G_TRANSITION", "C_TRANS", "yunuslama programı", CMD)
# --- RTA iç mimarisi
e("RTA_VALIDATOR", "RTA_PREDICTOR", "geçerli öneri", CMD)
e("RTA_VALIDATOR", "RTA_SELECTOR", "gelişmiş komut", CMD)
e("RTA_PREDICTOR", "RTA_FUTURE")
e("RTA_ENVELOPE", "RTA_CONSTRAINT")
e("RTA_FUTURE", "RTA_CONSTRAINT")
e("RTA_CONSTRAINT", "RTA_DECISION")
e("RTA_LATCH", "RTA_DECISION", "kilit", S)
e("RTA_HYST", "RTA_DECISION", "geri dönüş izni", S)
e("RTA_DECISION", "RTA_SELECTOR", "seçim", S)
e("RTA_DECISION", "RTA_REASON")
e("RTA_REASON", "RTA_LOGGER")
e("RTA_LOGGER", "BUS_EVENT", "rta olayları")
e("RTA_HEALTH", "BUS_HEALTH", "RTA sağlığı", S)
e("C_SAFETY", "RTA_SELECTOR", "güvenli komut", CMD)
e("RTA_SELECTOR", "BUS_COMMAND", "ValidatedCommand", CMD)
e("RTA_DECISION", "MD_CONTINGENCY", "RTA durumu", S)
e("RTA_DECISION", "SUP_SYSTEM", "RTA durumu", S)
# --- kontrol
e("BUS_COMMAND", "C_ATT", "yatış/yunuslama", CMD)
e("BUS_COMMAND", "C_VEL", "hava hızı", CMD)
e("C_POS", "C_ATT", "eğim", CMD)
e("C_TRANS", "C_ATT", "tutum hedefi", CMD)
e("C_TRANS", "C_VEL", "dikey itki", CMD)
e("C_ATT", "AL_ALLOCATOR", "moment isteği", CMD)
e("C_VEL", "AL_ALLOCATOR", "itki isteği", CMD)
e("EN_AVAIL", "C_VEL", "güç sınırı", S)
e("MD_FSM", "GNC_G", "mod -> güdüm seçimi", S)
e("MD_FSM", "GNC_C", "mod -> kontrol yasası", S)
# --- dağıtım ve şeritler
e("AL_EFFECTIVENESS", "AL_ALLOCATOR", "B(V,σ)")
e("AL_EFFECTIVENESS", "AL_HOVER_MARGIN")
e("BUS_HEALTH", "AL_ALLOCATOR", "sağlık vektörü", S)
e("BUS_HEALTH", "AL_HOVER_MARGIN", "sağlık", S)
e("AL_ALLOCATOR", "AL_LIMITER", "", CMD)
e("AL_LIMITER", "LA_OUT", "şerit önerisi", CMD)
e("AL_LIMITER", "LB_OUT", "şerit önerisi", CMD)
for L in "AB":
    e(f"L{L}_INPUT", f"L{L}_EST")
    e(f"L{L}_EST", f"L{L}_GUID")
    e(f"L{L}_GUID", f"L{L}_CTRL", "", CMD)
    e(f"L{L}_CTRL", f"L{L}_SAFETY", "", CMD)
    e(f"L{L}_SAFETY", f"L{L}_OUT", "", CMD)
    e(f"L{L}_OUT", "LANE_COMPARATOR", "", CMD)
    e(f"L{L}_OUT", "LC_CROSS", "", S)
    e(f"L{L}_OUT", "LANE_DIVERGENCE", "", S)
    e(f"L{L}_INPUT", "LANE_XDATA", "", S)
    e(f"LANE{L}", "LANE_HEARTBEAT", "kalp atışı", S)
e("LC_SENSORS", "LC_CROSS", "bağımsız durum")
e("LC_CROSS", "LC_CMD_MON")
e("LC_INTEGRITY", "LC_CMD_MON", "", S)
e("LANE_HEARTBEAT", "LC_WATCHDOG", "", S)
e("LC_WATCHDOG", "LANE_ISOLATION", "", S)
e("LC_CMD_MON", "LANE_ISOLATION", "", S)
e("LANE_XDATA", "LANE_ISOLATION", "", S)
e("LANE_DIVERGENCE", "LANE_ISOLATION", "", S)
e("LANE_TIMING", "LANE_ISOLATION", "", S)
e("TM_SCHED", "LANE_TIMING", "", S)
e("LANE_COMPARATOR", "LANE_VOTER", "", CMD)
e("LANE_ISOLATION", "LANE_VOTER", "yalıtılmış şerit", S)
e("LANE_ISOLATION", "FDIR_LANE", "şerit durumu", S)
e("LANE_VOTER", "AL_CMD_MGR", "oylanmış komut", CMD)
e("AL_CMD_MGR", "AL_HEALTH_GATE", "", CMD)
e("FDIR_RECOVERY", "AL_HEALTH_GATE", "FAILED -> dışla", S)
e("AL_HEALTH_GATE", "ACT_M", "itki komutları", CMD)
e("AL_HEALTH_GATE", "ACT_E", "sapma komutları", CMD)
# --- eyleyici -> araç (dijital ikiz bitki modeli) -> algı
e("ACT_M", "DT_ACTUATOR")
e("ACT_E", "DT_ACTUATOR")
e("ACT_M", "SEN_VH", "devir/akım geri beslemesi")
e("ACT_E", "SEN_VH", "konum geri beslemesi")
# --- FDIR omurgası
for dom in ("FDIR_SENSOR", "FDIR_MOTOR", "FDIR_ACTUATOR", "FDIR_NAV", "FDIR_POWER",
            "FDIR_COMM", "FDIR_LANE"):
    e(dom, "FDIR_DETECT", "", S)
e("FDIR_DETECT", "FDIR_ISOLATE", "", S)
e("FDIR_ISOLATE", "FDIR_CLASSIFY", "", S)
e("FDIR_CLASSIFY", "FDIR_SCORE", "", S)
e("FDIR_SCORE", "FDIR_SUP", "", S)
e("FDIR_SUP", "FDIR_RECOVERY", "", S)
e("FDIR_SUP", "FDIR_VHM", "ComponentHealth", S)
e("FDIR_VHM", "BUS_HEALTH", "VehicleHealth", S)
e("AL_HOVER_MARGIN", "FDIR_VHM", "kontrol otoritesi", S)
e("FDIR_RECOVERY", "MD_CONTINGENCY", "kurtarma önerisi", S)
# --- enerji
for src in ("EN_FC_MODEL", "EN_BATT_MODEL", "EN_SC_MODEL", "EN_SOLAR_MODEL"):
    e(src, "EN_SRC_MON")
e("EN_SRC_MON", "EN_AVAIL")
e("EN_AVAIL", "EN_ARBITRATION")
e("EN_DEMAND", "EN_ARBITRATION")
e("EN_ARBITRATION", "EN_MANAGER")
e("EN_MANAGER", "EN_RESERVE")
e("EN_THERMAL", "EN_SRC_HEALTH", "", S)
e("EN_SRC_MON", "EN_SRC_HEALTH", "", S)
e("EN_SRC_HEALTH", "EN_FAULT_DET", "", S)
e("EN_MANAGER", "EN_BUS_HEALTH", "PowerSplit", S)
e("EN_BUS_HEALTH", "EN_FAULT_DET", "", S)
e("EN_FAULT_DET", "FDIR_POWER", "", S)
e("EN_RESERVE", "FDIR_POWER", "rezerv uyarısı", S)
e("MD_FSM", "EN_EMERGENCY_POLICY", "acil mod", S)
e("EN_EMERGENCY_POLICY", "EN_ARBITRATION", "rezerv kilidi", S)
e("EN_RESERVE", "MD_CONTINGENCY", "eve dönüş/iniş enerjisi", S)
e("EN_RESERVE", "SUP_SYSTEM", "enerji uyarısı", S)
e("DT_ENERGY", "SEN_EN", "kaynak durumları")
# --- haberleşme
e("CO_GROUND", "CO_MSG_VALID", "uplink")
e("CO_MSG_VALID", "CO_AUTH")
e("CO_AUTH", "CO_SEQ")
e("CO_SEQ", "CO_CMD_ROUTER")
e("CO_CMD_ROUTER", "MD_FSM", "operatör mod isteği", CMD)
e("CO_CMD_ROUTER", "MC_MISSION_MGR", "görev güncellemesi", CMD)
e("CO_MESH", "CO_V2V")
e("BUS_TELEMETRY", "CO_TLM_ROUTER")
e("CO_TLM_ROUTER", "CO_GROUND", "downlink")
e("CO_TLM_ROUTER", "CO_MESH")
e("CO_GROUND", "CO_LINK_QUALITY", "", S)
e("CO_HEARTBEAT", "CO_HEALTH", "", S)
e("CO_LINK_QUALITY", "CO_HEALTH", "", S)
e("CO_HEALTH", "CO_FAILOVER", "", S)
e("CO_FAILOVER", "CO_GROUND", "yol seçimi", S)
e("CO_HEALTH", "FDIR_COMM", "bağlantı durumu", S)
e("CO_HEALTH", "MD_CONTINGENCY", "C2 kesinti süresi", S)
e("CO_HEALTH", "SUP_SYSTEM", "haberleşme durumu", S)
# --- mod, acil durum, preflight, denetçi
e("MD_TABLE", "MD_FSM", "izinli geçişler", S)
e("MD_RULES", "MD_CONTINGENCY", "öncelikli kurallar", S)
e("BUS_HEALTH", "MD_CONTINGENCY", "araç sağlığı + kontrol otoritesi", S)
e("MD_CONTINGENCY", "MD_FSM", "önerilen güvenli mod", S)
e("MD_FSM", "BUS_EVENT", "mod olayları")
e("MD_FSM", "SUP_SYSTEM", "uçuş modu", S)
e("BUS_HEALTH", "SUP_SYSTEM", "araç sağlığı", S)
e("NAV_SUPERVISOR", "SUP_SYSTEM", "nav bütünlüğü", S)
e("SUP_SYSTEM", "BUS_TELEMETRY", "sistem durumu")
e("SUP_SYSTEM", "BUS_EVENT", "system_state_changed")
for pid in ("CONFIG", "SENSOR", "NAV", "ENERGY", "CONTROL", "COMM", "MISSION", "SAFETY"):
    e(f"PF_{pid}", "PRE_SUPERVISOR", "", S)
e("CFG_MANAGER", "PF_CONFIG", "", S)
e("SEN_HEALTH", "PF_SENSOR", "", S)
e("NAV_SRC_MGR", "PF_NAV", "kaynak sayısı", S)
e("EN_MANAGER", "PF_ENERGY", "kullanılabilir enerji", S)
e("AL_HOVER_MARGIN", "PF_CONTROL", "hover marjı", S)
e("CO_HEALTH", "PF_COMM", "", S)
e("MC_MISSION_DB", "PF_MISSION", "rota", S)
e("CFG_SAFETY", "PF_SAFETY", "", S)
e("PRE_SUPERVISOR", "MD_FSM", "preflight_ok -> ARMED", S)
# --- zaman
e("TM_SIM_CLOCK", "TM_SYSTEM_TIME")
e("TM_SYSTEM_TIME", "TM_SENSOR_TS")
e("TM_SENSOR_TS", "TM_CONSISTENCY", "", S)
e("TM_CONSISTENCY", "LANE_TIMING", "saat kayması", S)
# --- yapılandırma
for cid in ("CFG_VEHICLE", "CFG_MISSION", "CFG_SAFETY", "CFG_NAV", "CFG_ENERGY", "CFG_SIM"):
    e(cid, "CFG_MANAGER")
e("CFG_VEHICLE", "AL_EFFECTIVENESS")
e("CFG_SAFETY", "RTA_ENVELOPE", "zarflar")
e("CFG_SAFETY", "MD_CONTINGENCY", "eşikler")
e("CFG_NAV", "NAV_INTEGRITY", "olasılıklar")
e("CFG_ENERGY", "EN_MANAGER")
e("CFG_MISSION", "MC_MISSION_DB")
e("CFG_MANAGER", "DT", "yapılandırma")
# --- kayıt
e("BUS_STATE", "FDR_STATE")
e("BUS_EVENT", "FDR_EVENT")
e("BUS_HEALTH", "FDR_HEALTH")
e("RTA_LOGGER", "FDR_RTA")
e("MD_FSM", "FDR_MODE")
e("NAV_SUPERVISOR", "FDR_NAV")
e("EN_MANAGER", "FDR_ENERGY")
for fid in ("STATE", "EVENT", "HEALTH", "RTA", "MODE", "NAV", "ENERGY"):
    e(f"FDR_{fid}", "FDR_REPLAY_IF")
e("FDR_REPLAY_IF", "FDR_DIAG")
e("FDR_DIAG", "FDR_POSTFLIGHT")
e("FDR_REPLAY_IF", "DT_REPLAY", "kayıtlar")
e("BUS_HEALTH", "DT_VEHICLE", "sağlık parametreleri", S)
# --- dijital ikiz
e("DT_SCENARIO", "DT_ENGINE")
e("DT_FAULT", "DT_ENGINE", "arıza takvimi", S)
e("DT_MC", "DT_ENGINE", "tohumlar")
e("DT_VEHICLE", "DT_6DOF")
e("DT_ENV", "DT_AERO")
e("DT_AERO", "DT_6DOF")
e("DT_ACTUATOR", "DT_PROP")
e("DT_PROP", "DT_6DOF")
e("DT_ENGINE", "DT_6DOF", "adım")
e("DT_6DOF", "DT_SENSOR", "gerçek durum")
e("DT_SENSOR", "SEN_INS")
e("DT_SENSOR", "SEN_AIR")
e("DT_SENSOR", "SEN_POS")
e("DT_PROP", "DT_ENERGY", "elektrik yükü")
e("DT_ENGINE", "DT_METRICS")
e("DT_REPLAY", "DT_METRICS")
e("DT_METRICS", "GCS", "simülasyon sonuçları")
# --- yer istasyonu
e("CO_GROUND", "GCS", "telemetri")
e("GCS_MISSION_PLANNER", "CO_GROUND", "görev/komut uplink", CMD)
e("FDR_POSTFLIGHT", "GCS_LOGS")
e("FDR_REPLAY_IF", "GCS_REPLAY")
e("GCS_ALERTS", "GCS_OVERVIEW")

EDGES: tuple[Edge, ...] = tuple(_E)

# Komut/gözetim yetkisini taşıyan geçitler: öneri katmanından eyleyiciye
# giden her yol bunlardan birinden geçmelidir.
AUTHORITY_GATES = frozenset({"RTA_SELECTOR", "LA_SAFETY", "LB_SAFETY", "MD_FSM"})

ARCHITECTURE = Architecture(GROUPS, COMPONENTS, EDGES, AUTHORITY_GATES)
