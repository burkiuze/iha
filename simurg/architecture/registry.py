"""SİMURG sistem-sistemleri (system-of-systems) mimarisinin bileşen kaydı (v2).

Tek doğruluk kaynağı: docs/15-sistem-mimarisi.md ve docs/mimari/*.md içindeki
diyagramlar, bileşen matrisleri, arıza zincirleri ve mimari-kod denetimi bu
kayıttan ÜRETİLİR (`python -m simurg.architecture --update-all`) ve
`tests/test_architecture.py` belge ile kaydın birebir aynı olduğunu, her kod
referansının gerçekten var olduğunu, kritik kod sınıflarının kayıtta yer
aldığını ve yetki değişmezlerini doğrular.

Durum anlamı:
  IMPLEMENTED  kodda var, simülasyona bağlı, otomatik testle doğrulanmış
  PARTIAL      basitleştirilmiş / kısmen modellenmiş / simülasyona bağlı değil
  UNVALIDATED  kodda var ama bu davranışı doğrulayan otomatik test/senaryo yok
  PLANNED      yalnızca mimaride (kod yok)

Bu kayıt bir yazılım / güvenlik / simülasyon mimari referansıdır; uçuşa hazır
donanım kablolaması, sürücü protokolü, ESC ayarı ya da kontrol kazancı içermez.
Kontrolcüler yazılım soyutlamasıdır.
"""

from __future__ import annotations

from .model import Architecture, Component, Edge, EdgeKind, FailureChain, Group, Status, View

I, P, U, X = Status.IMPLEMENTED, Status.PARTIAL, Status.UNVALIDATED, Status.PLANNED
D, CMD, S = EdgeKind.DATA, EdgeKind.COMMAND, EdgeKind.SUPERVISORY

HS = "NOMINAL/DEGRADED/FAILED/UNKNOWN"
LS = "NOMINAL/DEGRADED/ISOLATED/FAILED/UNKNOWN"
NA = "durumsuz (n/a)"

GROUPS: tuple[Group, ...] = (
    Group("GCS", "GROUND SEGMENT"),
    Group("COMM", "COMMUNICATION", (("COMM_LINK", "Bağlantılar"), ("COMM_PROC", "Mesaj işleme"),
                                    ("COMM_HEALTH", "Bağlantı sağlığı"))),
    Group("MC", "MISSION COMPUTER (yalnızca öneri; uçuş-kritik değil)"),
    Group("SEN", "SENSOR SUITE", (("SEN_INS", "Inertial / heading"), ("SEN_GNSS", "GNSS"),
                                  ("SEN_ALT", "Alternatif navigasyon girdileri"),
                                  ("SEN_VH", "Araç sağlık telemetrisi"),
                                  ("SEN_PIPE", "Ölçüm hattı (driver → bus)"))),
    Group("AIR", "AIR DATA"),
    Group("NAV", "NAVIGATION", (("NAV_INT", "Bütünlük (integrity)"),)),
    Group("EST", "STATE ESTIMATION"),
    Group("GUID", "GUIDANCE"),
    Group("CV", "COMMAND VALIDATION"),
    Group("RTA", "RUNTIME ASSURANCE (Simplex)", (("RTA_IN", "Girdiler"), ("RTA_CHK", "Denetim"),
                                                 ("RTA_SEL", "Seçim"), ("RTA_EXP", "Açıklama"))),
    Group("CTRL", "FLIGHT CONTROL (yazılım soyutlaması; kazanç içermez)"),
    Group("ALLOC", "CONTROL ALLOCATION"),
    Group("FCC", "TRIPLEX FLIGHT COMPUTERS", (("FCC_A", "FCC A"), ("FCC_B", "FCC B"),
                                              ("FCC_C", "FCC C / Independent Monitor"),
                                              ("FCC_X", "Cross-lane"))),
    Group("ACT", "ACTUATOR SYSTEM (simülasyon soyutlaması)",
          (("ACT_CMD", "Komut yönetimi"), ("ACT_M", "Motor Group"), ("ACT_E", "Elevon Group"),
           ("ACT_FB", "Geri besleme"))),
    Group("AV", "AIR VEHICLE (parametrik model)"),
    Group("FDIR", "FDIR"),
    Group("VH", "VEHICLE HEALTH"),
    Group("EN", "POWER / ENERGY", (("EN_SRC", "Kaynak modelleri"), ("EN_FLOW", "Güç akışı"),
                                   ("EN_HEALTH", "Enerji sağlığı"))),
    Group("MODE", "MODE / CONTINGENCY MANAGEMENT"),
    Group("PRE", "PREFLIGHT SUPERVISOR"),
    Group("SUP", "SYSTEM SUPERVISION"),
    Group("TIME", "TIME / SYNCHRONIZATION"),
    Group("BUS", "DATA BUS (mantıksal)"),
    Group("CFG", "CONFIGURATION"),
    Group("FDR", "FLIGHT DATA RECORDER"),
    Group("DT", "DIGITAL TWIN", (("DT_RUN", "Koşum altyapısı"), ("DT_PLANT", "Bitki modelleri"),
                                 ("DT_ANA", "Analiz"))),
)

_C: list[Component] = []


def c(id: str, name: str, group: str, resp: str, inp: str, out: str, health: str,
      status: Status, code: tuple[str, ...] = (), *, sub: str = "", proposal: bool = False,
      note: str = "", fail: str = "", master: bool = False, red: str = "") -> None:
    _C.append(Component(id, name, group, resp, inp, out, health, status, code, sub, proposal,
                        note, fail, master, red))


# ======================================================================= GROUND
c("GCS_OPERATOR", "Operator Console", "GCS", "Operatör görünümü ve komut girişi (yalnızca istek)",
  "telemetri, olaylar", "görev/mod isteği", HS, X,
  fail="Konsol yok -> araç son geçerli görevde kalır; bağlantı kaybı kuralı işler", master=True)
c("GCS_MISSION_PLAN", "Mission Planning", "GCS", "Görev ve geofence tanımı", "operatör", "görev profili",
  NA, P, ("simurg/sim/scenario.py::MissionProfile",), note="Senaryo dosyasıyla tanımlanır",
  fail="Geçersiz görev uçuş öncesi denetimde reddedilir")
c("GCS_HEALTH_VIEW", "Health / RTA / Nav Panels", "GCS", "Sağlık, RTA, nav bütünlüğü, enerji görünümü",
  "telemetri", "operatör uyarıları", NA, X, fail="Görünüm yok -> karar araç üzerinde kalır")
c("GCS_REPLAY", "Replay & Log Viewer", "GCS", "Kaydın zaman çizelgesi ve açıklaması",
  "simurg.sim-log", "zaman çizelgesi", NA, P, ("simurg/sim/__main__.py::main",),
  note="CLI: python -m simurg.sim replay", fail="Bilinmeyen şema reddedilir")
c("GCS_FLEET", "Fleet / Swarm View", "GCS", "Çoklu araç görünümü", "telemetri", "görünüm", NA, X,
  fail="n/a")

# ======================================================================= COMMUNICATION
c("CO_GROUND", "Ground Link", "COMM", "Yer bağlantısı soyutlaması (C2 var/yok)", "uplink/downlink",
  "mesajlar, bağlantı durumu", HS, I, ("simurg/sim/link.py::LinkModel",), sub="COMM_LINK",
  fail="Kayıp -> LINK_LOST olayı, 30 s sonra RETURN kuralı", master=True)
c("CO_V2V", "Vehicle-to-Vehicle Link", "COMM", "Araçlar arası mesajlaşma soyutlaması", "mesajlar",
  "komşu durumları", HS, X, sub="COMM_LINK", fail="Kayıp -> sürü koordinasyonu öneri üretmez")
c("CO_MSG_VALID", "Message Validator", "COMM", "Şema/aralık denetimi", "uplink", "geçerli mesaj",
  HS, X, sub="COMM_PROC", fail="Geçersiz mesaj düşürülür ve olay üretilir")
c("CO_SEQ", "Sequence Monitor", "COMM", "Sıra numarası / tekrar / kayıp denetimi", "mesajlar",
  "sıra durumu", HS, X, sub="COMM_PROC", fail="Tekrar/eski mesaj reddedilir")
c("CO_CMD_ROUTER", "Command Router", "COMM", "Doğrulanmış yer isteklerini hedefe yönlendirme",
  "geçerli mesaj", "mod/görev isteği", HS, X, sub="COMM_PROC",
  fail="Yönlendirilemeyen istek uygulanmaz", master=True)
c("CO_TLM_ROUTER", "Telemetry Router", "COMM", "Telemetrinin bağlantılara yönlendirilmesi",
  "telemetri yolu", "downlink", HS, X, sub="COMM_PROC", fail="Telemetri düşer; araç davranışı etkilenmez")
c("CO_HEARTBEAT", "Heartbeat Monitor", "COMM", "Bağlantı yaşam sinyali ve kesinti süresi",
  "bağlantı", "kesinti süresi", HS, I, ("simurg/sim/link.py::LinkModel",), sub="COMM_HEALTH",
  fail="Kalp atışı yok -> kesinti zamanlayıcısı başlar")
c("CO_LINK_QUALITY", "Link Quality", "COMM", "Gecikme/kayıp ölçümü", "bağlantı", "kalite metriği",
  HS, X, sub="COMM_HEALTH", fail="Ölçüm yok -> kalite UNKNOWN")
c("CO_LINK_HEALTH", "Link Health", "COMM", "C2 var/yok + kesinti süresi -> haberleşme FDIR",
  "kalp atışı", "bağlantı sağlığı", HS, I, ("simurg/fdir/reports.py::communication_fdir",),
  sub="COMM_HEALTH", fail="C2 yok -> FAILED (iyimser varsayım yok)", master=True)
c("CO_FAILOVER", "Failover Manager", "COMM", "Yedek bağlantıya geçiş", "bağlantı sağlığı",
  "yol seçimi", HS, X, sub="COMM_HEALTH", red="planlanan çift bağlantı",
  fail="Yedek yok -> bağlantı kaybı kuralı")

# ======================================================================= MISSION COMPUTER
MC_FAIL = "Arıza/hatalı çıktı -> öneri doğrulayıcıda reddedilir; uçuş güvenliği RTA + güvenlik kontrolcüsünde"
c("MC_MISSION_MGR", "Mission Manager", "MC", "Görev ilerleyişi; nominal mod İSTEĞİ (FSM'e)",
  "durum, enerji rezervi, nav bütünlüğü", "mod isteği, hedef", NA, I,
  ("simurg/sim/mission.py::MissionManager",), proposal=True, fail=MC_FAIL, master=True)
c("MC_PLANNER", "High-Level Planner", "MC", "Görev hedeflerinden ara nokta rotası", "görev",
  "ara noktalar", NA, P, ("simurg/sim/scenario.py::MissionProfile",), proposal=True,
  note="Rota senaryoda sabit; planlayıcı yok", fail=MC_FAIL)
c("MC_SEARCH", "Search Planner", "MC", "Arama-tarama deseni (şerit/spiral)", "arama alanı",
  "ara noktalar", NA, X, proposal=True, fail=MC_FAIL)
c("MC_PERCEPTION", "Perception", "MC", "Gözlem verisinden olay çıkarımı (sivil gözlem)", "kamera",
  "algı olayları", HS, X, proposal=True, fail=MC_FAIL)
c("MC_AI", "Mission AI", "MC", "YZ çıkarımı -> yalnızca öneri", "algı, durum", "öneri", HS, X,
  proposal=True, fail=MC_FAIL, master=True)
c("MC_MAPPING", "Mapping", "MC", "Görev haritası", "algı + konum", "harita", NA, X, proposal=True,
  fail=MC_FAIL)
c("MC_SWARM", "Swarm Coordination", "MC", "Enerji farkındalıklı görev dağıtımı (CBBA referansı)",
  "ajanlar, görevler", "görev ataması", NA, P, ("simurg/swarm/auction.py::allocate",),
  proposal=True, note="Simülasyon motoruna bağlı değil", fail=MC_FAIL)
c("MC_PROPOSAL", "CommandProposal Output", "MC", "Tek çıkış: zaman damgalı, kaynaklı öneri zarfı",
  "güdüm çıktısı", "CommandProposal", NA, I, ("simurg/safety/command_validator.py::CommandProposal",),
  proposal=True, fail="Bayat/geçersiz zarf doğrulayıcıda reddedilir", master=True)
c("MC_HEALTH", "Mission Health", "MC", "Görev bilgisayarı sağlığı (öneri akışı geçerliliği)",
  "doğrulayıcı sonuçları", "görev bilg. sağlığı", HS, I,
  ("simurg/fdir/reports.py::mission_computer_fdir",), proposal=True,
  fail="Kalıcı geçersiz öneri (>3 s) -> FAILED -> CONTINGENCY")

# ======================================================================= SENSOR SUITE
for k in "ABC":
    c(f"SEN_IMU_{k}", f"IMU {k}", "SEN", f"Şerit {k} için bağımsız açısal hız/ivme", "hareket",
      "ham IMU", HS, X, sub="SEN_INS", red="triplex", master=(k == "A"),
      note="Simülasyonda tutum gerçek durumdan alınır (kusursuz kestirici varsayımı)",
      fail="Tek IMU arızası -> şerit karşılaştırması ile yalıtım (planlanan)")
c("SEN_MAG", "Magnetometer", "SEN", "Manyetik yön gözlemi", "manyetik alan", "yön", HS, X,
  sub="SEN_INS", fail="Bozulma -> yön kaynağı dışlanır (planlanan)")
c("SEN_GNSS_A", "GNSS A", "SEN", "Mutlak konum", "uydu sinyali (soyut)", "konum + kovaryans",
  HS, I, ("simurg/sim/sensors.py::SimulatedPositionProvider",), sub="SEN_GNSS", master=True,
  red="4 bağımsız konum kaynağından biri",
  fail="Kayıp -> kaynak kullanılamaz; sapma -> RAIM dışlaması")
c("SEN_GNSS_B", "GNSS B / Alternate Input", "SEN", "İkinci GNSS alıcısı", "uydu sinyali (soyut)",
  "konum", HS, X, sub="SEN_GNSS", fail="Planlanan")
c("SEN_VIO", "Camera / VIO", "SEN", "Görsel-ataletsel göreli konum", "kamera", "konum + kovaryans",
  HS, I, ("simurg/sim/sensors.py::SimulatedPositionProvider",), sub="SEN_ALT", master=True,
  fail="Kayıp/sapma -> kaynak kullanılamaz / dışlanır")
c("SEN_TRN", "TRN", "SEN", "Arazi referanslı konum", "yükseklik haritası", "konum + kovaryans",
  HS, I, ("simurg/sim/sensors.py::SimulatedPositionProvider",), sub="SEN_ALT",
  fail="Kayıp/sapma -> kaynak kullanılamaz / dışlanır")
c("SEN_MAGNAV", "MagNav", "SEN", "Manyetik anomali haritası ile konum", "manyetometre",
  "konum + kovaryans", HS, I, ("simurg/sim/sensors.py::SimulatedPositionProvider",), sub="SEN_ALT",
  fail="Kayıp/sapma -> kaynak kullanılamaz / dışlanır")
c("SEN_CELESTIAL", "Celestial Navigation", "SEN", "Güneş/yıldız ile yön sınırlama", "kamera",
  "yön gözlemi", HS, X, sub="SEN_ALT", fail="Planlanan")
c("SEN_RPM", "Motor / ESC Telemetry", "SEN", "Motor devri (ESC telemetrisinin yalnızca devir kısmı)",
  "motor çıkışı", "devir", HS, I, ("simurg/sim/sensors.py::SensorModel",), sub="SEN_VH",
  note="Akım/sıcaklık modellenmez",
  fail="Geri dönüşü yok: kaybında motor FDIR kör -> sensör alanı FAILED")
c("SEN_ACT_POS", "Actuator Position Feedback", "SEN", "Elevon konum geri beslemesi", "yüzey",
  "ölçülen konum", HS, I, ("simurg/sim/actuators.py::ActuatorState",), sub="SEN_VH",
  fail="Takılı/devre dışı yüzey -> konum artığı -> FAILED")
c("SEN_POWER_TLM", "Power Telemetry", "SEN", "Kaynak gücü, SoC, karşılanamayan güç", "enerji modeli",
  "PowerSplit, EnergyState", HS, P, ("simurg/power/energy_manager.py::PowerSplit",), sub="SEN_VH",
  note="Model durumu doğrudan okunur; ölçüm gürültüsü yok",
  fail="Sonlu olmayan değer -> enerji alanı UNKNOWN")
c("SEN_TEMP", "Temperature / Health Sensors", "SEN", "Motor/batarya/FC sıcaklığı", "termal",
  "sıcaklık", HS, X, sub="SEN_VH", fail="Planlanan (termal model yok)")
c("SEN_DRIVER", "Sensor Driver", "SEN", "Sensör okuma soyutlaması (ham ölçüm)", "sensör modeli",
  "SensorMeasurement", HS, I, ("simurg/sim/sensors.py::SensorModel",), sub="SEN_PIPE", master=True,
  fail="Dropout -> valid=False, NaN değer")
c("SEN_TIMESTAMP", "Timestamp", "SEN", "Zaman damgası denetimi + tazelik", "ham ölçüm",
  "tazelik (s)", HS, I, ("simurg/sensing/pipeline.py::SensorChannel",), sub="SEN_PIPE",
  fail="Gelecek/bayat damga -> STALE, güven 0")
c("SEN_SIGNAL_VALID", "Signal Validation", "SEN", "Geçerlilik bayrağı + sonluluk", "ölçüm",
  "VALID/INVALID", HS, I, ("simurg/sensing/pipeline.py::SensorChannel",), sub="SEN_PIPE",
  fail="Geçersiz/NaN -> INVALID, kullanılamaz", master=True)
c("SEN_PLAUSIBILITY", "Plausibility Check", "SEN", "Fiziksel aralık + değişim hızı sınırı",
  "geçerli ölçüm", "VALID/IMPLAUSIBLE", HS, I, ("simurg/sensing/pipeline.py::ChannelSpec",),
  sub="SEN_PIPE", fail="Sıçrama/aralık dışı -> IMPLAUSIBLE", master=True)
c("SEN_HEALTH", "Sensor Health", "SEN", "Kalıcılık sayaçlı kanal sağlığı", "doğrulama sonucu",
  HS, HS, I, ("simurg/sensing/pipeline.py::SensorChannel",), sub="SEN_PIPE",
  fail="Ölçümsüz kanal UNKNOWN; ardışık kötü ölçüm -> FAILED", master=True)
c("SEN_MEAS_BUS", "Measurement Bus", "SEN", "Kaynak başına son ölçüm + meta veri", "Measurement",
  "son ölçümler, sağlık özeti", HS, P, ("simurg/sensing/pipeline.py::MeasurementBus",
                                         "simurg/sensing/pipeline.py::SensorPipeline"), sub="SEN_PIPE",
  note="Gözlem amaçlı: navigasyon bugün ham ölçümü kullanır (PARTIAL entegrasyon)",
  fail="Bayat kaynak -> check_freshness ile STALE")

# ======================================================================= AIR DATA
c("AIR_BARO_A", "Barometer A", "AIR", "Barometrik irtifa", "statik basınç", "irtifa", HS, I,
  ("simurg/sim/sensors.py::SensorModel",),
  fail="Dropout -> ataletsel dikey entegrasyon geri dönüşü")
c("AIR_BARO_B", "Barometer B", "AIR", "İkinci barometre", "statik basınç", "irtifa", HS, X,
  red="planlanan ikili", fail="Planlanan")
c("AIR_PITOT", "Pitot / Airspeed", "AIR", "Hava hızı", "dinamik basınç", "hava hızı", HS, I,
  ("simurg/sim/sensors.py::SensorModel",),
  fail="Dropout -> yer hızı kestirimi + SENSOR_DEGRADED olayı")
c("AIR_ADC", "Air Data Abstraction", "AIR", "Hava verisi seçimi ve açık geri dönüş politikası",
  "baro, pitot", "irtifa, hava hızı (+ bozulma bayrağı)", HS, I,
  ("simurg/sim/airdata.py::AirDataSystem",), master=True,
  fail="Eski değer sessizce kullanılmaz; geri dönüş kaynağı + olay")
c("AIR_ALT_FALLBACK", "Altitude Fallback", "AIR", "Baro yokken ataletsel dikey hız entegrasyonu",
  "son irtifa, dikey hız", "kestirilmiş irtifa", HS, U, ("simurg/sim/airdata.py::AirDataSystem",),
  note="Kodda var; bu yolu çalıştıran senaryo/test yok",
  fail="Uzun süreli kullanımda sürüklenme (sınırsız)")

# ======================================================================= NAVIGATION
c("NAV_SRC_MGR", "Navigation Source Manager", "NAV", "Sağlayıcılardan ölçüm toplama, kullanılamayanları ayırma",
  "konum ölçümleri", "aday ölçümler, kullanılamayan kaynaklar", HS, I,
  ("simurg/nav/providers.py::NavigationSystem",), master=True, red="4 kaynak",
  fail="Ölçüm yok/NaN -> kaynak kullanılamaz (NAV_SOURCE_UNAVAILABLE)")
c("NAV_MEAS_VALID", "Measurement Validator", "NAV", "Geçerli ve sonlu ölçüm/kovaryans seçimi",
  "aday ölçümler", "doğrulanmış ölçümler", HS, I, ("simurg/nav/providers.py::NavigationSystem",),
  fail="Sonlu olmayan ölçüm füzyona girmez")
c("NAV_INTEGRITY", "Integrity Monitor", "NAV", "Ki-kare tutarlılık testi", "kaynaklar + çözüm",
  "test istatistiği, eşik", HS, I, ("simurg/nav/integrity.py::IntegrityMonitor",), sub="NAV_INT",
  master=True, fail="< 2 kaynak -> bütünlük DOĞRULANAMAZ (integrity_ok=False)")
c("NAV_FD", "Fault Detection", "NAV", "T > eşik tespiti", "test istatistiği", "arıza var/yok", HS, I,
  ("simurg/nav/integrity.py::test_statistic",), sub="NAV_INT", fail="Tespit -> dışlama denemesi")
c("NAV_FE", "Fault Exclusion", "NAV", "Leave-one-out ile hatalı kaynağı dışlama", "kaynak kümesi",
  "dışlanan kaynaklar", HS, I, ("simurg/nav/integrity.py::IntegrityMonitor",), sub="NAV_INT",
  master=True, fail="Dışlama sonrası tutarsızlık sürerse bütünlük kaybı")
c("NAV_PL", "Protection / Confidence Estimate", "NAV", "PL = k_md·sqrt(λmax(P)); güven = 1 - PL/AL",
  "kovaryans", "PL, güven", HS, I, ("simurg/nav/integrity.py::IntegrityMonitor",), sub="NAV_INT",
  fail="PL > alarm limiti -> bütünlük yok")
c("NAV_SUPERVISOR", "Navigation Supervisor", "NAV", "Nav olayları ve bütünlük geçişleri",
  "çözüm", "nav olayları", HS, P, ("simurg/sim/engine.py::SimulationEngine",), master=True,
  note="Motor içinde (_navigation)", fail="İlk çözümden önce bütünlük varsayılmaz")
c("NAV_HEALTH", "NavigationHealth", "NAV", "Navigasyon alanı FDIR raporu", "NavigationSolution",
  "FdirReport(navigation)", HS, I, ("simurg/fdir/reports.py::navigation_fdir",),
  fail="Çözüm yok -> UNKNOWN; bütünlük yok -> FAILED")

# ======================================================================= STATE ESTIMATION
c("EST_INERTIAL", "Inertial Propagation", "EST", "Kaynak yokken son çözümü hızla ilerletme",
  "son çözüm, hız", "ilerletilmiş konum, büyüyen PL", HS, I,
  ("simurg/nav/providers.py::NavigationSystem",),
  fail="integrity_ok=False; PL zamanla büyür")
c("EST_ESTIMATOR", "State Estimator", "EST", "Ters kovaryans ağırlıklı konum füzyonu",
  "doğrulanmış ölçümler", "konum + kovaryans", HS, P, ("simurg/nav/integrity.py::fuse",),
  master=True, note="Yatay konum füzyonu; tam ESKF planlanan", fail="Kaynaksız -> ataletsel ilerletme")
c("EST_ATTITUDE", "Attitude Estimate", "EST", "Tutum kestirimi", "IMU", "kuaterniyon", HS, X,
  note="Simülasyon gerçek tutumu kullanır", fail="Planlanan (IMU karşılaştırmalı)")
c("EST_POSITION", "Position Estimate", "EST", "Yatay konum + koruma seviyesi", "füzyon",
  "konum", HS, I, ("simurg/core/types.py::NavigationSolution",), fail="Bütünlüksüz konum işaretlenir")
c("EST_VELOCITY", "Velocity Estimate", "EST", "Hız kestirimi", "IMU/kaynaklar", "hız", HS, P,
  ("simurg/core/types.py::NavigationSolution",), note="Simülasyonda gerçek hız kullanılır",
  fail="Planlanan kestirici")
c("EST_SOLUTION", "Navigation Solution", "EST", "Bütünlük bilgili çözüm nesnesi",
  "kestirim + bütünlük", "NavigationSolution", HS, I, ("simurg/core/types.py::NavigationSolution",),
  master=True, fail="Bütünlük alanı ayrı: konum var ama güvenilmeyebilir (state != integrity)")
c("EST_VEHICLE_STATE", "VehicleState", "EST", "Merkezi durum (tek doğruluk kaynağı)",
  "kestirim, enerji, mod", "VehicleState", NA, I, ("simurg/core/types.py::VehicleState",),
  master=True, fail="Sonlu olmayan durum -> SimulationError (sessiz değil)")

# ======================================================================= GUIDANCE
c("G_MISSION", "Mission Guidance", "GUID", "Ara noktaya rota + irtifa ÖNERİSİ (gelişmiş kontrolcü)",
  "durum, hedef", "Command önerisi", NA, I, ("simurg/control/guidance.py::MissionGuidance",),
  proposal=True, master=True, fail="Hatalı öneri -> doğrulayıcı / RTA tarafından engellenir")
c("G_INTENT", "Trajectory Intent", "GUID", "Yörünge niyeti (hedef dizisi + kısıtlar)", "görev",
  "niyet", NA, X, proposal=True, fail="Planlanan")
c("G_WAYPOINT", "Waypoint Guidance", "GUID", "Ara nokta ilerleyişi ve aktif hedef", "konum",
  "aktif hedef", NA, I, ("simurg/sim/mission.py::MissionManager",), proposal=True,
  fail="Bütünlük yokken ilerleme durur (LOITER_HOLD)")
c("G_LOITER", "Loiter / Hold Guidance", "GUID", "Sabit yatışlı bekleme önerisi", "durum",
  "Command önerisi", NA, I, ("simurg/control/guidance.py::MissionGuidance",), proposal=True,
  fail="Hatalı öneri -> doğrulayıcı / RTA")
c("G_RETURN", "Return Guidance", "GUID", "Eve dönüş önerisi", "konum, ev", "Command önerisi", NA, I,
  ("simurg/control/guidance.py::MissionGuidance",), proposal=True, fail="Hatalı öneri -> doğrulayıcı / RTA")
c("G_TRANSITION", "Transition Guidance", "GUID", "VTOL<->sabit kanat programı ve iptal mantığı",
  "hız, yunuslama, irtifa, doyma", "TransitionStatus", "iptal gerekçesi", I,
  ("simurg/control/transition.py::TransitionCoordinator",), master=True,
  fail="Ölçüt dışı -> geçiş iptali (TRANSITION_ABORTED) ve askıya dönüş")

# ======================================================================= COMMAND VALIDATION
c("CV_PROPOSAL", "Proposal Envelope", "CV", "Öneri zarfı: içerik, kaynak, zaman, mod, tür",
  "öneri", "CommandProposal", NA, I, ("simurg/safety/command_validator.py::CommandProposal",),
  fail="Zarf dışı (çıplak) komut eski yol: yalnızca şema+sınır")
c("CV_SCHEMA", "Schema Validation", "CV", "Tip ve sonluluk", "CommandProposal", "geçerli/INVALID",
  NA, I, ("simurg/safety/command_validator.py::CommandValidator",), master=True,
  fail="INVALID -> reddedilir, kırpılmaz")
c("CV_FRESHNESS", "Timestamp / Freshness", "CV", "Gelecek/bayat zaman damgası", "zaman damgası",
  "geçerli/STALE", NA, I, ("simurg/safety/command_validator.py::ProposalLimits",), master=True,
  fail="STALE -> reddedilir (donmuş görev bilgisayarı)")
c("CV_MODE", "Mode Compatibility", "CV", "Öneri modu == aktif mod ve mod öneri kabul eder",
  "mod", "geçerli/INCOMPATIBLE", NA, I, ("simurg/safety/command_validator.py::PROPOSAL_MODES",),
  master=True, fail="INCOMPATIBLE -> reddedilir")
c("CV_BOUNDS", "Command Bounds", "CV", "Fiziksel akla yatkınlık (zarf DEĞİL)", "komut",
  "geçerli/INVALID", NA, I, ("simurg/safety/command_validator.py::ProposalLimits",), master=True,
  fail="Sınır dışı -> reddedilir, kırpılmaz")
c("CV_AUTHORITY", "Authority Check", "CV", "Kayıtlı öneri kaynağı + yetkili komut türü",
  "kaynak, tür", "geçerli/UNKNOWN/UNAUTHORIZED", NA, I,
  ("simurg/safety/command_validator.py::PROPOSAL_SOURCES",
   "simurg/safety/command_validator.py::ALLOWED_KINDS"), master=True,
  fail="Bilinmeyen kaynak / eyleyici seviyesi komut -> reddedilir")
c("CV_VALIDATOR", "Command Validator", "CV", "Aşamaları sırayla uygular; sınıf + aşama + gerekçe",
  "CommandProposal", "geçerli Command ya da ValidationResult(red)", NA, I,
  ("simurg/safety/command_validator.py::CommandValidator",), master=True,
  fail="Red -> RTA o adımda yalnızca güvenlik kontrolcüsünü doğrular (gecersiz_oneri)")

# ======================================================================= RTA
c("RTA_IN_ADV", "Advanced Command Input", "RTA", "Doğrulanmış gelişmiş öneri girişi", "doğrulayıcı",
  "AC komutu", NA, I, ("simurg/safety/rta.py::RuntimeAssurance",), sub="RTA_IN",
  fail="Öneri yok -> güvenlik kontrolcüsü")
c("RTA_IN_SAFE", "Safety Controller Input", "RTA", "Güvenli öneri girişi", "güvenlik kontrolcüsü",
  "SC komutu", NA, I, ("simurg/safety/rta.py::RuntimeAssurance",), sub="RTA_IN",
  fail="Her zaman mevcut olmalı (basit, durumsuz yasa)")
c("RTA_IN_STATE", "Vehicle State Input", "RTA", "Zarf görünümü", "VehicleState", "EnvelopeState", NA, I,
  ("simurg/safety/rta.py::EnvelopeState",), sub="RTA_IN",
  fail="NaN -> gecersiz_durum ihlali (güvenli sayılmaz)")
c("RTA_ENVELOPE", "Safety Envelope", "RTA", "Yumuşak/sert zarf tanımı", "yapılandırma", "zarflar", NA, I,
  ("simurg/safety/rta.py::Envelope",), sub="RTA_CHK", master=True,
  fail="Tutarsız zarf -> uçuş öncesi RTA kontrolü başarısız")
c("RTA_CONSTRAINT", "Constraint Monitor", "RTA", "İrtifa, hız, yatış, yunuslama, geofence kısıtları",
  "durum", "ihlal listesi, pay", NA, I, ("simurg/safety/rta.py::Envelope",), sub="RTA_CHK",
  fail="Sonlu olmayan değer -> ihlal")
c("RTA_PREDICTOR", "State Predictor", "RTA", "Öneri uygulanırsa ufuk sonundaki durum", "durum, öneri",
  "öngörülen durum", NA, I, ("simurg/safety/rta.py::KinematicPredictor",), sub="RTA_CHK", master=True,
  fail="Muhafazakâr (kötüleşme yönü)")
c("RTA_PRED_CHECK", "Predicted Violation Check", "RTA", "Öngörülen durum vs yumuşak zarf",
  "öngörülen durum", "öngörülen ihlaller", NA, I, ("simurg/safety/rta.py::RuntimeAssurance",),
  sub="RTA_CHK", master=True, fail="İhlal -> SC")
c("RTA_CUR_CHECK", "Current Violation Check", "RTA", "Mevcut durum vs sert zarf", "durum",
  "mevcut ihlaller", NA, I, ("simurg/safety/rta.py::RuntimeAssurance",), sub="RTA_CHK", master=True,
  fail="İhlal -> SC + kilit")
c("RTA_SELECTOR", "Command Selector", "RTA", "NİHAİ GÜVENLİK KAPISI: tek ValidatedCommand üreticisi",
  "AC, SC, karar", "ValidatedCommand (mühürlü)", NA, I, ("simurg/safety/rta.py::ValidatedCommand",),
  sub="RTA_SEL", master=True, fail="Kilitliyken AC seçilemez; sert ihlalde AC yetkisi yok")
c("RTA_LATCH", "Latch Manager", "RTA", "Sert ihlalde uçuş sonuna dek SC'ye kilit", "sert ihlal",
  "kilit", "kilitli/serbest", I, ("simurg/safety/rta.py::RuntimeAssurance",), sub="RTA_SEL",
  master=True, fail="Kilit yalnızca yerde reset()")
c("RTA_HYST", "Recovery Hysteresis", "RTA", "AC'ye dönüş için ardışık güvenli çevrim", "zarf payı",
  "geri dönüş izni", NA, I, ("simurg/safety/rta.py::RuntimeAssurance",), sub="RTA_SEL",
  fail="Titreşimli anahtarlama önlenir")
c("RTA_REASON", "Decision Reason Generator", "RTA", "Açıklanabilir gerekçe", "ihlaller",
  "SafetyDecision", NA, I, ("simurg/safety/rta.py::SafetyDecision",), sub="RTA_EXP",
  fail="Gerekçesiz karar olay şemasında yasak (testli)")
c("RTA_RECORDER", "Intervention Recorder", "RTA", "Müdahale/geri dönüş/kilit olayları", "SafetyDecision",
  "rta_* olayları", NA, I, ("simurg/sim/engine.py::SimulationEngine",), sub="RTA_EXP", master=True,
  fail="Olay kaybı yok (senkron olay yolu)")
c("RTA_HEALTH", "RTA Runtime Health", "RTA", "RTA'nın kendi çalışma/zamanlama sağlığı", "çevrim",
  "RTA sağlığı", HS, X, sub="RTA_EXP", fail="Planlanan (bekçi köpeği)")
c("RTA_SELFTEST", "RTA Self-Test", "RTA", "Uçuş öncesi: sert ihlalde SC seçiliyor mu", "zarflar",
  "geçti/kaldı", NA, I, ("simurg/sim/preflight.py::PreflightSupervisor",), sub="RTA_EXP",
  fail="Başarısız -> ARMED yok")

# ======================================================================= FLIGHT CONTROL
c("C_MODE_SEL", "Control Law Selector", "CTRL", "Moda göre kontrol yasası seçimi", "mod, doğrulanmış komut",
  "aktif yasa", NA, I, ("simurg/sim/vehicle_control.py::VehicleController",), master=True,
  fail="Sabit kanat yasası doğrulanmış komutsuz çalışmaz (SafetyInvariantError)")
c("C_POS", "Position Control", "CTRL", "Askıda yatay konum tutma -> eğim isteği", "konum, hedef",
  "eğim", NA, P, ("simurg/control/flight_controller.py::FlightController",),
  fail="Doyma -> saturation_fraction raporu")
c("C_VEL", "Velocity Control", "CTRL", "Hava hızı / dikey hız -> itki isteği", "hız hatası, güç sınırı",
  "itki isteği", NA, P, ("simurg/control/flight_controller.py::FlightController",), master=True,
  fail="Güç açığında itki ölçeklenir")
c("C_ATT", "Attitude Control", "CTRL", "Tutum hatası -> moment isteği", "tutum hedefi",
  "moment isteği", "kontrol kaybı zamanlayıcısı", I,
  ("simurg/control/flight_controller.py::FlightController",), master=True,
  note="Araştırma soyutlaması; kazançlar uçuş için ayarlı değildir",
  fail="Kalıcı tutum hatası / otorite açığı -> controllable=False -> PARAŞÜT kuralı")
c("C_TRANS", "Transition Control", "CTRL", "Geçişte yunuslama programı + dikey itki", "TransitionStatus",
  "tutum hedefi + itki", NA, I, ("simurg/sim/vehicle_control.py::VehicleController",),
  fail="İptal -> askıya dönüş")
c("C_SAFETY", "Safety Controller", "CTRL", "Basit, doğrulanabilir güvenli öneri (kanat düz, irtifa, geofence)",
  "durum, geofence", "güvenli Command", NA, I, ("simurg/control/guidance.py::SafetyController",),
  master=True, fail="Tekil yasa: SPOF adayı (bkz. denetim)")

# ======================================================================= ALLOCATION
c("AL_DEMAND", "Control Demand", "ALLOC", "İtki + moment isteği vektörü", "kontrol yasaları",
  "v_des", NA, I, ("simurg/control/effectiveness.py::body_to_alloc",), master=True,
  fail="Sonlu olmayan istek -> SimulationError")
c("AL_EFFECTIVENESS", "Effectiveness B(V, σ)", "ALLOC", "Rejime bağlı etkinlik matrisi",
  "hız, σ, yapılandırma", "ControlRegime", NA, I,
  ("simurg/control/effectiveness.py::ScheduledEffectiveness",), fail="İç motorlar seyirde katlı (B sütunu 0)")
c("AL_AUTHORITY", "Available Authority", "ALLOC", "Askı marjı (itki/ağırlık) ve kalan otorite",
  "sağlık vektörü", "hover marjı", "bilinmeyen eyleyici havada = çalışmıyor", I,
  ("simurg/sim/health.py::HealthSupervisor",), master=True,
  fail="Marj < eşik -> hover_feasible=False -> acil iniş kuralı")
c("AL_ALLOCATOR", "Health-Aware Allocation", "ALLOC", "Sağlık ağırlıklı RPI dağıtımı",
  "v_des, sağlık, rejim", "eyleyici komutu, doyma, artık", NA, I,
  ("simurg/control/allocation.py::ControlAllocator",), master=True,
  fail="Doyma -> artık (allocation residual) raporlanır")
c("AL_LIMITER", "Command Limiter", "ALLOC", "Eyleyici sınırlarına kırpma", "dağıtım çıktısı",
  "sınırlı komut", NA, I, ("simurg/control/allocation.py::ControlAllocator",),
  fail="Sınır dışı komut eyleyiciye gitmez")
c("AL_RESIDUAL", "Allocation Residual / Saturation", "ALLOC", "İstenen - elde edilen; doyma oranı",
  "dağıtım", "artık, doyma", NA, I, ("simurg/control/allocation.py::AllocationResult",),
  fail="Kalıcı otorite açığı -> kontrol kaybı zamanlayıcısı")

# ======================================================================= TRIPLEX FCC
for L in "AB":
    hosted = L == "A"
    lst = P if hosted else X
    lcode = ("simurg/sim/engine.py::SimulationEngine",) if hosted else ()
    lnote = ("Simülasyonda tek hesap A şeridinde koşar; B/C onun kopyasını önerir"
             if hosted else "Farklı mimarili bağımsız uygulama planlanan")
    for sid, nm, resp in (("INPUT", "Input Manager", "Girdi toplama ve tazelik"),
                          ("SNAP", "State Snapshot", "Çevrim başı tutarlı durum görüntüsü"),
                          ("GUID", "Guidance", "Şerit içi güdüm (GUIDANCE işlevleri)"),
                          ("CTRL", "Control", "Şerit içi kontrol + dağıtım (FLIGHT CONTROL + ALLOCATION)"),
                          ("HMON", "Health Monitor", "Şeridin öz-sağlığı ve kalp atışı")):
        c(f"FCC_{L}_{sid}", nm, "FCC", resp, "şerit içi", "şerit içi", LS, lst, lcode, sub=f"FCC_{L}",
          note=lnote, fail="Şerit hatası -> çıktı uyuşmazlığı ya da kalp atışı kaybı -> yalıtım",
          red="triplex")
    c(f"FCC_{L}_OUT", "Output Proposal", "FCC", "Şeridin eyleyici komutu önerisi", "şerit kontrolü",
      "LaneOutput", LS, P, ("simurg/sim/triplex.py::TriplexFlightComputer",), sub=f"FCC_{L}",
      note="Simülasyonda aynı hesabın kopyası + şerit arızası enjeksiyonu", master=True, red="triplex",
      fail="Sapma -> ISOLATED; kalp atışı yok -> FAILED")
c("FCC_C_MONITOR", "Independent Monitor", "FCC", "Bağımsız durumla çıktıları karşılaştırma",
  "IMU C, şerit çıktıları", "uyuşmazlık", LS, X, sub="FCC_C",
  fail="Planlanan (bugün C şeridi de kopya önerir)")
c("FCC_C_TIMING", "Timing Monitor", "FCC", "Şerit çevrim süreleri ve son tarihler", "çizelge",
  "zamanlama ihlali", LS, X, sub="FCC_C", fail="Planlanan")
c("FCC_C_WATCHDOG", "Watchdog", "FCC", "Kalp atışı zaman aşımı", "kalp atışları", "şerit canlı mı",
  LS, I, ("simurg/fdir/lanes.py::TriplexVoter",), sub="FCC_C", master=True,
  fail="Zaman aşımı -> FAILED (mandallı)")
c("FCC_C_DIVERGENCE", "Divergence Detection", "FCC", "Ardışık uyuşmazlık sayacı", "fark vektörü",
  "ayrışan şerit", LS, I, ("simurg/fdir/lanes.py::TriplexVoter",), sub="FCC_C",
  fail="Kalıcı ayrışma -> ISOLATED")
c("FCC_C_OUT", "Output Proposal (C)", "FCC", "Üçüncü çıktı (oylamada hakem)", "şerit C",
  "LaneOutput", LS, P, ("simurg/sim/triplex.py::TriplexFlightComputer",), sub="FCC_C", master=True,
  red="triplex", note="Simülasyonda kopya", fail="Sapma -> ISOLATED")
c("FCC_COMPARATOR", "Cross-Lane Comparator", "FCC", "Şerit çıktılarını medyana göre karşılaştırma",
  "A/B/C çıktıları", "fark vektörü", LS, I, ("simurg/fdir/lanes.py::TriplexVoter",), sub="FCC_X",
  master=True, fail="Tek şerit sapması medyanla maskelenir")
c("FCC_VOTER", "Lane Voter", "FCC", "Üçlüde medyan, ikilide uyuşma + son çıktı hakemi, tekli",
  "çıktılar, durumlar", "oylanmış eyleyici komutu", LS, I, ("simurg/fdir/lanes.py::TriplexVoter",),
  sub="FCC_X", master=True, red="triplex",
  fail="Şerit yok -> çıktı yok -> controllable=False -> PARAŞÜT kuralı")
c("FCC_ISOLATION", "Lane Isolation Manager", "FCC", "NOMINAL/DEGRADED/ISOLATED/FAILED/UNKNOWN durumları",
  "karşılaştırma, bekçi", "şerit durumları + olay", LS, I, ("simurg/fdir/lanes.py::LaneState",),
  sub="FCC_X", master=True, fail="ISOLATED/FAILED mandallı: oylayıcıya nominal dönmez")

# ======================================================================= ACTUATOR SYSTEM
c("ACT_CMD_MGR", "Actuator Command Manager", "ACT", "Oylanmış komutun zaman damgasıyla dağıtımı",
  "oylanmış komut", "ActuatorCommand", NA, I, ("simurg/sim/actuators.py::ActuatorCommand",),
  sub="ACT_CMD", master=True, fail="Çıktı yoksa son oylanmış komut tutulur + kontrol kaybı bayrağı")
c("ACT_HEALTH_GATE", "Actuator Health Gate", "ACT", "FAILED eyleyici nominal dağıtıma ALINMAZ (komut 0)",
  "sağlık vektörü", "kapılı dağıtım", NA, I, ("simurg/control/allocation.py::ControlAllocator",),
  sub="ACT_CMD", master=True, note="Simülasyonda dağıtıcı içinde (oylama öncesi) uygulanır",
  fail="ACTUATOR_EXCLUDED olayı + yeni hover marjı")
c("ACT_MOTOR_GROUP", "Motor Group", "ACT", "8 motor DEP (iç 4'ü seyirde katlanır)", "itki komutları",
  "itkiler", HS, I, ("simurg/sim/actuators.py::ActuatorModel",), sub="ACT_M", master=True,
  red="8 motor; herhangi tek motor kaybı askıda tolere",
  fail="Tek motor kaybı tolere; aynı uçta iki motor -> hover yok -> süzülerek acil iniş")
for m in ("M1U", "M2U", "M3U", "M4U", "M1L", "M2L", "M3L", "M4L"):
    c(f"ACT_{m}", f"Motor {m}", "ACT", "Motor + pervane (gecikme, tepki, doyma)", "normalize itki",
      "itki, devir", "NOMINAL/DEGRADED/STUCK/OFFLINE", I, ("simurg/sim/actuators.py::ActuatorModel",),
      sub="ACT_M", red="motor grubu", fail="Verim kaybı -> DEGRADED; devir yok -> FAILED -> dağıtım dışı")
c("ACT_ELEVON_GROUP", "Elevon Group", "ACT", "4 elevon (kutu kanat)", "sapma komutları", "sapmalar",
  HS, I, ("simurg/sim/actuators.py::ActuatorModel",), sub="ACT_E", master=True, red="4 yüzey",
  fail="Tek yüzey kaybı -> DEGRADED; tümü -> FAILED (itki diferansiyeli)")
for el in ("E1U", "E2U", "E1L", "E2L"):
    c(f"ACT_{el}", f"Elevon {el}", "ACT", "Kontrol yüzeyi (soyutlama)", "normalize sapma",
      "sapma, konum", "NOMINAL/DEGRADED/STUCK/OFFLINE", I, ("simurg/sim/actuators.py::ActuatorModel",),
      sub="ACT_E", red="elevon grubu", fail="Takılı/devre dışı -> konum artığı -> FAILED -> dağıtım dışı")
c("ACT_FEEDBACK", "Actuator Feedback", "ACT", "Çıkış, beklenen çıkış, konum", "eyleyici modeli",
  "ActuatorState", NA, I, ("simurg/sim/actuators.py::ActuatorState",), sub="ACT_FB", master=True,
  fail="Geri besleme yok -> ilgili FDIR UNKNOWN")
c("ACT_MOTOR_HEALTH", "Motor Health", "ACT", "Motor başına sağlık + verim kestirimi", "devir artığı",
  "sağlık vektörü (motor)", HS, I, ("simurg/fdir/monitor.py::MotorHealthMonitor",), sub="ACT_FB",
  fail="Gözlenmemiş motor havada UNKNOWN")
c("ACT_SATURATION", "Saturation State", "ACT", "Doyma oranı", "dağıtım", "saturation_fraction", NA, I,
  ("simurg/sim/vehicle_control.py::VehicleController",), sub="ACT_FB",
  fail="Kalıcı doyma geçiş iptali ölçütüne girer")

# ======================================================================= AIR VEHICLE
c("AV_AIRFRAME", "Box-Wing Tail-Sitter Airframe", "AV", "Kutu kanat, kuyruksuz, uç levhaları",
  "-", "kütle/atalet/geometri", NA, P, ("simurg/core/config.py::VehicleConfig",), master=True,
  note="Parametrik; yapısal model yok", fail="Yapısal arıza modellenmez")
c("AV_DEP", "Distributed Electric Propulsion", "AV", "8 motor yerleşimi ve itki ekseni", "-",
  "motor geometrisi", NA, P, ("simurg/core/config.py::VehicleConfig",), red="8 motor",
  fail="Motor arızası eyleyici modelinde")
c("AV_PARACHUTE", "Recovery Parachute", "AV", "Son çare kurtarma (sürükleme modeli)", "PARACHUTE modu",
  "sürükleme kuvveti", NA, I, ("simurg/sim/engine.py::SimulationEngine",),
  fail="Açılma gecikmesi 1 s; açılmama modellenmez")
c("AV_LANDING", "Endplate Landing Gear", "AV", "Uç levhaları ile dikey iniş / temas sınıflandırma",
  "temas hızı, tutum", "Touchdown", NA, I, ("simurg/sim/ground.py::classify_touchdown",),
  fail="Sert temas -> IMPACT olayı")

# ======================================================================= FDIR
c("FDIR_SUP", "FDIR Supervisor", "FDIR", "Sekiz alan FDIR'ini çalıştırma, raporları birleştirme",
  "alan girdileri", "8 FdirReport", HS, I, ("simurg/fdir/vehicle_health.py::VehicleHealthModel",),
  master=True, fail="Bilgisi olmayan alan UNKNOWN raporlar")
FDIR_DOMS = (
    ("SENSOR", "Sensor FDIR", "sensor_fdir", "Kanal sağlıkları", True),
    ("NAV", "Navigation FDIR", "navigation_fdir", "NavigationSolution", True),
    ("FCC", "FCC FDIR", "fcc_fdir", "Şerit durumları", True),
    ("MOTOR", "Motor FDIR", "motor_fdir", "Motor durumları + hover fizibilitesi", True),
    ("ACTUATOR", "Actuator FDIR", "actuator_fdir", "Yüzey durumları", True),
    ("ENERGY", "Energy FDIR", "energy_fdir", "EnergyState, rezerv, güç açığı", True),
    ("COMM", "Communication FDIR", "communication_fdir", "Bağlantı durumu", True),
    ("MC", "Mission Computer FDIR", "mission_computer_fdir", "Öneri akışı geçerliliği", True),
)
for did, nm, fn, inp, ms in FDIR_DOMS:
    c(f"FDIR_{did}", nm, "FDIR", "Tespit, yalıtım, sınıf, güven, sağlık, önerilen bozulma", inp,
      "FdirReport", HS, I, (f"simurg/fdir/reports.py::{fn}",), master=ms,
      fail="Gözlenmeyen durum -> UNKNOWN (NOMINAL değil)")
c("FDIR_MOTOR_MON", "Motor Monitor (CUSUM)", "FDIR", "Devir artığı CUSUM + verim EMA", "beklenen/ölçülen devir",
  "ComponentHealth", HS, I, ("simurg/fdir/monitor.py::MotorHealthMonitor",),
  fail="Sabit kısmi hasar DEGRADED kalır; FAILED mandallı")
c("FDIR_SURFACE_MON", "Surface Monitor", "FDIR", "Komut-konum artığı kalıcılığı", "beklenen/ölçülen konum",
  "ComponentHealth", "NOMINAL/FAILED", P, ("simurg/fdir/monitor.py::SurfaceMonitor",),
  note="Yüzey verim kaybı konumdan gözlenemez", fail="Kalıcı artık -> FAILED")
c("FDIR_REPORT", "FDIR Report Format", "FDIR", "Standart rapor: tespit/yalıtım/sınıf/güven/sağlık/öneri",
  "-", "FdirReport", NA, I, ("simurg/fdir/reports.py::FdirReport",), fail="n/a")

# ======================================================================= VEHICLE HEALTH
c("VH_MANAGER", "Vehicle Health Manager", "VH", "Alan raporlarını araç seviyesine birleştirme",
  "8 FdirReport + kontrol otoritesi", "VehicleHealth", "NOMINAL/DEGRADED/CONTINGENCY/CRITICAL/UNKNOWN", I,
  ("simurg/fdir/vehicle_health.py::VehicleHealthModel",), master=True,
  fail="UNKNOWN asla NOMINAL değil; değişim VEHICLE_HEALTH_CHANGED olayı")
c("VH_LEVEL", "Health Level Classifier", "VH", "CRITICAL > CONTINGENCY > UNKNOWN > DEGRADED > NOMINAL",
  "alan durumları", "seviye + reasons[]", NA, I, ("simurg/fdir/vehicle_health.py::classify",),
  master=True, fail="n/a (saf fonksiyon)")
c("VH_CONTROL_AUTH", "Control Authority Domain", "VH", "Kontrol edilebilirlik + askı otoritesi",
  "controllable, hover marjı", "kontrol alanı sağlığı", HS, I,
  ("simurg/fdir/vehicle_health.py::VehicleHealthModel",), fail="Kontrol kaybı -> CRITICAL")
c("VH_NOT_MODELED", "Not-Modeled Register", "VH", "Modellenmeyen alanların açık listesi (termal, IMU)",
  "-", "not_modeled", NA, I, ("simurg/fdir/vehicle_health.py::NOT_MODELED",),
  fail="'Modellenmedi' != 'sağlıklı' ayrımı korunur")

# ======================================================================= POWER / ENERGY
c("EN_FC", "Fuel Cell Abstraction", "EN", "PEM gücü, eğim sınırı, H2 tüketimi (soyut)", "hedef güç",
  "FC gücü", HS, I, ("simurg/power/energy_manager.py::fc_efficiency",), sub="EN_SRC", master=True,
  red="hibrit kaynak", note="Fiziksel hidrojen sistemi kurulumu kapsam dışı",
  fail="Bozunum -> güç ölçeği düşer")
c("EN_BATT", "Battery Abstraction", "EN", "SoC, deşarj sınırı", "güç", "SoC", HS, I,
  ("simurg/power/energy_manager.py::EnergyManager",), sub="EN_SRC", master=True, red="hibrit kaynak",
  fail="Kapasite kaybı kalıcı; rezerv uyarısı")
c("EN_SC", "Supercapacitor Abstraction", "EN", "Tepe güç tamponu", "güç", "SoC", HS, I,
  ("simurg/power/energy_manager.py::EnergyManager",), sub="EN_SRC", red="hibrit kaynak",
  fail="Bara akım sınırında tükenir")
c("EN_SOLAR", "Solar Abstraction", "EN", "Güneş katkısı", "güneş girdisi", "güç", HS, P,
  ("simurg/power/energy_manager.py::EnergyManager",), sub="EN_SRC",
  note="Birim testli; simülasyon motorunda 0 W", fail="Yok sayılır (0 W)")
c("EN_SRC_HEALTH", "Source Health", "EN", "Kaynak bozunum özeti", "ölçekler", "health 0..1", HS, I,
  ("simurg/power/energy_manager.py::EnergyManager",), sub="EN_HEALTH", fail="< 1 -> DEGRADED")
c("EN_AVAIL", "Power Availability", "EN", "Kaynak başına anlık güç sınırı", "SoC, ölçekler",
  "kullanılabilir güç", NA, P, ("simurg/power/energy_manager.py::EnergyManager",), sub="EN_FLOW",
  fail="Talep > kullanılabilir -> karşılanamayan güç")
c("EN_DEMAND", "Power Demand", "EN", "İtki + aviyonik elektrik yükü", "itki, hız", "anlık talep", NA, P,
  ("simurg/sim/propulsion.py::PropulsionModel",), sub="EN_FLOW", note="İleri tahmin planlanan",
  fail="n/a")
c("EN_ARBITRATION", "Power Arbitration", "EN", "Frekans ayrıştırmalı kaynak paylaşımı", "talep, sınırlar",
  "PowerSplit", NA, I, ("simurg/power/energy_manager.py::EnergyManager",), sub="EN_FLOW", master=True,
  fail="Açık > 0,5 s -> güç alanı FAILED; itki ölçeklenir")
c("EN_MANAGER", "Energy Manager", "EN", "Hibrit enerji yönetimi, EnergyState", "talep", "EnergyState",
  HS, I, ("simurg/power/energy_manager.py::EnergyManager",), sub="EN_FLOW", master=True,
  fail="Sonlu olmayan kestirim -> UNKNOWN")
c("EN_RESERVE", "Reserve Estimator", "EN", "Eve dönüş/iniş enerjisi ve uyarı histerezisi",
  "kullanılabilir enerji, mesafe", "ReserveAssessment", "bilinmeyen enerji -> uyarı", I,
  ("simurg/power/reserve.py::ReserveMonitor",), sub="EN_HEALTH", master=True,
  fail="Uyarı -> görev iptali + RETURN")
c("EN_BUS_HEALTH", "Power Bus Health", "EN", "Karşılanamayan güç, itki güç faktörü", "PowerSplit",
  "bara sağlığı", HS, P, ("simurg/sim/engine.py::SimulationEngine",), sub="EN_HEALTH",
  note="Güç dengesi düzeyinde; gerilim modellenmez", fail="Kalıcı açık -> FAILED")
c("EN_THERMAL", "Thermal Health", "EN", "Batarya/FC sıcaklığı", "güç", "sıcaklık", HS, X, sub="EN_HEALTH",
  fail="Planlanan")
c("EN_EMERGENCY", "Emergency Energy State", "EN", "Acil modlarda rezervin kullanıma açılması", "mod",
  "rezerv kilidi", NA, I, ("simurg/power/energy_manager.py::EnergyManager",), sub="EN_HEALTH",
  fail="Rezerv yalnızca acil durumda")

# ======================================================================= MODE / CONTINGENCY
c("MD_FSM", "Flight Mode Machine", "MODE", "13 mod; mod DEĞİŞİMİNİN TEK YOLU (yetki geçidi)",
  "mod istekleri, bağlam", "aktif mod, TransitionRecord", NA, I,
  ("simurg/modes/flight_modes.py::FlightModeMachine",), master=True,
  fail="Tablo dışı / koruması sağlanmayan istek reddedilir + MODE_REJECTED")
c("MD_TABLE", "Transition Table", "MODE", "Geçiş + koruma koşulları (tek kaynak)", "-", "izinli geçişler",
  NA, I, ("simurg/modes/flight_modes.py::TRANSITIONS",), fail="PARACHUTE havada terminal")
c("MD_CONTINGENCY", "Contingency Manager", "MODE", "Önerilen güvenli mod + gerekçe + öncelik + zaman",
  "araç sağlığı, nav bütünlüğü, enerji, kontrol otoritesi, haberleşme, RTA", "ContingencyDecision", NA, I,
  ("simurg/modes/flight_modes.py::ContingencyManager",), master=True,
  note="Sağlık seviyesi ve RTA kilidi kayıtlı girdi; kural tetikleyicisi değil",
  fail="İstek FSM korumasına tabidir; reddedilirse alt kurala inilmez")
c("MD_RULES", "Contingency Rule Table", "MODE", "Öncelikli kurallar (docs/08 §3)", "-", "kurallar", NA, I,
  ("simurg/modes/flight_modes.py::CONTINGENCY_RULES",), fail="n/a")
c("MD_INPUTS", "Contingency Input Snapshot", "MODE", "Kararla birlikte kaydedilen girdiler", "Context",
  "inputs", NA, I, ("simurg/modes/flight_modes.py::CONTINGENCY_INPUTS",), fail="n/a")

# ======================================================================= PREFLIGHT
c("PRE_SUPERVISOR", "Preflight Supervisor", "PRE", "11 kontrol; kritik başarısızlıkta ARMED yok",
  "kontrol sonuçları", "PreflightReport, preflight_ok", "geçti/kaldı", I,
  ("simurg/sim/preflight.py::PreflightSupervisor",), master=True,
  fail="Bilinmeyen durum geçmiş sayılmaz; PREFLIGHT_FAILED + kalkış yok")
for pid, nm in (("CONFIG", "Configuration Check"), ("SENSOR", "Sensor Check"),
                ("NAV", "Navigation Check"), ("FCC", "FCC Lane Check"), ("RTA", "RTA Check"),
                ("CTRL", "Control Authority Check"), ("ACT", "Actuator Health Check"),
                ("ENERGY", "Energy Check"), ("COMM", "Communication Check"),
                ("MISSION", "Mission Validation"), ("REC", "Recorder Check")):
    c(f"PF_{pid}", nm, "PRE", f"Uçuş öncesi: {nm}", "ilgili alt sistem durumu", "PreflightCheck",
      "geçti/kaldı + gerekçe", I, ("simurg/sim/preflight.py::CHECK_NAMES",),
      fail="Kritik: başarısızsa ARMED yok")

# ======================================================================= SYSTEM SUPERVISION
c("SUP_SYSTEM", "System Supervisor", "SUP", "NORMAL/DEGRADED/CONTINGENCY/EMERGENCY; EYLEYİCİ SÜRMEZ",
  "araç sağlığı, RTA, mod, nav, enerji, haberleşme, kontrol otoritesi, FDIR", "SystemAssessment",
  "sistem durumu", I, ("simurg/sim/supervisor.py::SystemSupervisor",), master=True,
  fail="Yalnızca değerlendirir; değişim SYSTEM_STATE_CHANGED")

# ======================================================================= TIME
c("TM_CLOCK", "System Clock", "TIME", "Monoton simülasyon zamanı (sabit adım)", "-", "t", NA, I,
  ("simurg/sim/engine.py::SimulationEngine",), master=True, fail="Geri giden zaman yok (testli)")
c("TM_SENSOR_TS", "Sensor Timestamp Manager", "TIME", "Ölçümlere zaman damgası + tazelik", "ölçümler",
  "zaman damgalı ölçümler", NA, I, ("simurg/core/types.py::SensorMeasurement",
                                     "simurg/sensing/pipeline.py::SensorChannel"),
  fail="Gelecek/bayat damga -> STALE")
c("TM_CONSISTENCY", "Clock Consistency", "TIME", "Şerit/sensör saat tutarlılığı", "zaman damgaları",
  "saat kayması", HS, X, fail="Planlanan")
c("TM_SCHEDULER", "Scheduler", "TIME", "Sabit 14 adımlı tick sırası", "-", "TICK_ORDER", NA, I,
  ("simurg/sim/engine.py::TICK_ORDER",), master=True, fail="Sıra sabit ve testli")
c("TM_SCHED_HEALTH", "Scheduler Health", "TIME", "Çevrim süresi/son tarih izleme", "çizelge",
  "zamanlama ihlali", HS, X, fail="Planlanan (simülasyon gerçek zamanlı değil)")
c("TM_TIMING_MON", "Timing Monitor", "TIME", "Şerit ve füzyon zamanlama izleme", "zaman damgaları",
  "zamanlama sağlığı", HS, X, fail="Planlanan")

# ======================================================================= DATA BUS
for bid, nm, resp, st, code in (
        ("STATE", "State Bus", "VehicleState / NavigationSolution dağıtımı", P, ("simurg/core/types.py::VehicleState",)),
        ("MEAS", "Measurement Bus", "Doğrulanmış ölçümler", I, ("simurg/sensing/pipeline.py::MeasurementBus",)),
        ("HEALTH", "Health Bus", "FdirReport / VehicleHealth", P, ("simurg/fdir/vehicle_health.py::VehicleHealth",)),
        ("COMMAND", "Command Bus", "ValidatedCommand -> kontrol", P, ("simurg/sim/vehicle_control.py::ControlInputs",)),
        ("EVENT", "Event Bus", "Senkron, sıralı olay yayını", I, ("simurg/core/events.py::EventBus",)),
        ("TLM", "Telemetry Bus", "Telemetri ve özet durum", P, ("simurg/sim/recorder.py::SimulationRecorder",))):
    c(f"BUS_{bid}", nm, "BUS", resp, "yayıncılar", "aboneler", NA, st, code, master=True,
      note="Mantıksal kanal; süreç içi nesne geçişi" if st is P else "",
      fail="Senkron: abone hatası yutulmaz, yukarı fırlatılır" if bid == "EVENT" else "n/a")

# ======================================================================= CONFIGURATION
c("CFG_MANAGER", "Configuration Manager", "CFG", "Değişmez (frozen) yapılandırmaların sağlanması",
  "senaryo", "yapılandırmalar", "geçersiz -> ConfigurationError", P,
  ("simurg/core/config.py::VehicleConfig",), note="Dağıtık dataclass'lar",
  fail="Uçuşta güvenlik parametresi değiştirilemez (frozen, testli)")
c("CFG_SAFETY", "Safety Configuration", "CFG", "Güvenlik eşikleri", "-", "SafetyConfig", NA, I,
  ("simurg/core/config.py::SafetyConfig",), master=True, fail="Tutarsızlık -> uçuş öncesi RTA kontrolü")
c("CFG_VEHICLE", "Vehicle Parameters", "CFG", "Kütle, atalet, eyleyiciler", "-", "VehicleConfig", NA, I,
  ("simurg/core/config.py::VehicleConfig",), fail="Geçersiz -> ConfigurationError")

# ======================================================================= FDR
c("FDR_CORE", "Flight Data Recorder", "FDR", "Kayıpsız olay + periyodik görüntü; sürümlü şema",
  "olay yolu, durum", "simurg.sim-log v1", NA, I, ("simurg/sim/recorder.py::SimulationRecorder",),
  master=True, fail="Bilinmeyen şema reddedilir; uçuş öncesi kayıt kontrolü")
for rid, nm, ch in (("STATE", "State Recorder", "state"), ("HEALTH", "Health Recorder", "health"),
                    ("MODE", "Mode Recorder", "mode"), ("FDIR", "FDIR Recorder", "fdir"),
                    ("RTA", "RTA Recorder", "rta"), ("NAV", "Navigation Recorder", "navigation"),
                    ("ENERGY", "Energy Recorder", "energy"), ("CMD", "Command Recorder", "command"),
                    ("FCC", "FCC Lane Recorder", "fcc")):
    c(f"FDR_{rid}", nm, "FDR", f"Mantıksal kayıt kanalı: {ch}", "kayıt", "kanal geçmişi", NA, I,
      ("simurg/sim/recorder.py::RECORDER_CHANNELS",), fail="Kanal tek kaydın görünümüdür (sıra korunur)")
c("FDR_EXPLAIN", "Decision Explainer", "FDR", "Neden RTA? neden şerit B? neden RETURN? neden dağıtım dışı?",
  "kayıt", "why_* yanıtları", NA, I, ("simurg/sim/replay.py::ReplaySession",), master=True,
  fail="Gerekçesiz güvenlik olayı test tarafından reddedilir")

# ======================================================================= DIGITAL TWIN
for did, nm, sub, st, code, ms, fail in (
        ("SCENARIO", "Scenario Manager", "DT_RUN", I, ("simurg/sim/scenarios.py::SCENARIOS",), True,
         "Geçersiz senaryo hiç koşturulmaz"),
        ("ENGINE", "Simulation Engine", "DT_RUN", I, ("simurg/sim/engine.py::SimulationEngine",), True,
         "Sayısal hata -> sim_failed + SimulationError"),
        ("FAULTS", "Fault Schedule / Injection", "DT_RUN", I, ("simurg/sim/faults.py::FaultInjector",), True,
         "Geçersiz arıza hedefi senaryoyu reddeder"),
        ("MC", "Monte Carlo Runner", "DT_RUN", I, ("simurg/sim/montecarlo.py::MonteCarloRunner",), False,
         "Tohumla yeniden üretilebilir"),
        ("ENV", "Environment Model", "DT_PLANT", I, ("simurg/sim/environment.py::ConstantEnvironment",), True, "n/a"),
        ("PARAMS", "Vehicle Parameters", "DT_PLANT", I, ("simurg/core/config.py::VehicleConfig",), False, "n/a"),
        ("SENSORS", "Sensor Models", "DT_PLANT", I, ("simurg/sim/sensors.py::SensorModel",), False, "n/a"),
        ("NAVMODEL", "Navigation Model", "DT_PLANT", I, ("simurg/sim/sensors.py::SimulatedPositionProvider",), False, "n/a"),
        ("ENERGY", "Energy Model", "DT_PLANT", I, ("simurg/power/energy_manager.py::EnergyManager",), False, "n/a"),
        ("ACTUATORS", "Actuator Models", "DT_PLANT", I, ("simurg/sim/actuators.py::ActuatorModel",), False, "n/a"),
        ("COMMS", "Communication Model", "DT_PLANT", P, ("simurg/sim/link.py::LinkModel",), False, "Yalnızca var/yok"),
        ("FCCMODEL", "FCC Lane Model", "DT_PLANT", P, ("simurg/sim/triplex.py::TriplexFlightComputer",), False,
         "Şeritler kopya; ortak mod hatası gösterilemez"),
        ("AERO", "Aerodynamic Model", "DT_PLANT", I, ("simurg/aero/model.py::AnalyticAeroModel",
                                                      "simurg/aero/model.py::TableAeroModel"), False,
         "Sentetik katsayılar"),
        ("DYN", "Vehicle Dynamics (6-DOF)", "DT_PLANT", I, ("simurg/sim/dynamics.py::RigidBodyDynamics",), True,
         "Sonlu olmayan durum -> SimulationError"),
        ("METRICS", "Metrics", "DT_ANA", I, ("simurg/sim/metrics.py::compute_metrics",), True, "n/a"),
        ("REPLAY", "Replay", "DT_ANA", I, ("simurg/sim/replay.py::ReplaySession",), True, "n/a")):
    c(f"DT_{did}", nm, "DT", nm + " (simülasyon; uçuşa elverişlilik kanıtı değildir)",
      "senaryo/yapılandırma", "simülasyon çıktısı", NA, st, code, sub=sub, master=ms, fail=fail)

COMPONENTS: tuple[Component, ...] = tuple(_C)

# ======================================================================= EDGES
_E: list[Edge] = []


def e(src: str, dst: str, label: str = "", kind: EdgeKind = D) -> None:
    _E.append(Edge(src, dst, label, kind))


# --- yer segmenti + haberleşme (soldan)
e("GCS_OPERATOR", "CO_GROUND", "istek uplink", CMD)
e("GCS_MISSION_PLAN", "CO_GROUND", "görev", CMD)
e("CO_GROUND", "CO_MSG_VALID", "uplink", CMD)
e("CO_MSG_VALID", "CO_SEQ", "", CMD)
e("CO_SEQ", "CO_CMD_ROUTER", "", CMD)
e("CO_CMD_ROUTER", "MD_FSM", "operatör mod isteği", CMD)
e("CO_CMD_ROUTER", "MC_MISSION_MGR", "görev güncellemesi", CMD)
e("CO_TLM_ROUTER", "CO_GROUND", "downlink")
e("CO_GROUND", "GCS_HEALTH_VIEW", "telemetri")
e("CO_V2V", "MC_SWARM", "komşu durumları")
e("CO_GROUND", "CO_HEARTBEAT", "", S)
e("CO_HEARTBEAT", "CO_LINK_HEALTH", "kesinti süresi", S)
e("CO_LINK_QUALITY", "CO_LINK_HEALTH", "", S)
e("CO_LINK_HEALTH", "CO_FAILOVER", "", S)
e("CO_FAILOVER", "CO_GROUND", "yol seçimi", S)
e("BUS_TLM", "CO_TLM_ROUTER")
# --- sensör hattı
for s in ("SEN_IMU_A", "SEN_IMU_B", "SEN_IMU_C", "SEN_MAG", "SEN_GNSS_A", "SEN_GNSS_B", "SEN_VIO",
          "SEN_TRN", "SEN_MAGNAV", "SEN_CELESTIAL", "SEN_RPM", "SEN_ACT_POS", "SEN_POWER_TLM",
          "SEN_TEMP", "AIR_BARO_A", "AIR_BARO_B", "AIR_PITOT"):
    e(s, "SEN_DRIVER")
e("SEN_DRIVER", "SEN_TIMESTAMP")
e("TM_SENSOR_TS", "SEN_TIMESTAMP", "zaman", S)
e("SEN_TIMESTAMP", "SEN_SIGNAL_VALID")
e("SEN_SIGNAL_VALID", "SEN_PLAUSIBILITY")
e("SEN_PLAUSIBILITY", "SEN_HEALTH")
e("SEN_HEALTH", "SEN_MEAS_BUS", "Measurement + meta veri")
e("SEN_MEAS_BUS", "BUS_MEAS")
e("SEN_HEALTH", "FDIR_SENSOR", "kanal sağlıkları", S)
# --- hava verisi
e("AIR_BARO_A", "AIR_ADC")
e("AIR_BARO_B", "AIR_ADC")
e("AIR_PITOT", "AIR_ADC")
e("AIR_ADC", "AIR_ALT_FALLBACK", "baro yok", S)
e("AIR_ADC", "EST_VEHICLE_STATE", "irtifa, hava hızı")
# --- navigasyon + kestirim
e("BUS_MEAS", "NAV_SRC_MGR", "konum ölçümleri")
e("SEN_GNSS_A", "NAV_SRC_MGR", "ham ölçüm (bugün)")
e("SEN_VIO", "NAV_SRC_MGR", "ham ölçüm (bugün)")
e("SEN_TRN", "NAV_SRC_MGR", "ham ölçüm (bugün)")
e("SEN_MAGNAV", "NAV_SRC_MGR", "ham ölçüm (bugün)")
e("NAV_SRC_MGR", "NAV_MEAS_VALID")
e("NAV_MEAS_VALID", "EST_ESTIMATOR", "doğrulanmış ölçümler")
e("SEN_IMU_A", "EST_ATTITUDE", "IMU")
e("EST_ESTIMATOR", "EST_POSITION")
e("EST_INERTIAL", "EST_POSITION", "kaynaksız ilerletme")
e("EST_ATTITUDE", "EST_SOLUTION")
e("EST_POSITION", "EST_SOLUTION")
e("EST_VELOCITY", "EST_SOLUTION")
e("EST_ESTIMATOR", "NAV_INTEGRITY", "füzyon + kovaryans")
e("NAV_INTEGRITY", "NAV_FD")
e("NAV_FD", "NAV_FE")
e("NAV_FE", "NAV_PL")
e("NAV_FE", "NAV_SRC_MGR", "dışlanan kaynaklar", S)
e("NAV_PL", "EST_SOLUTION", "PL, güven, bütünlük")
e("EST_SOLUTION", "NAV_SUPERVISOR")
e("EST_SOLUTION", "NAV_HEALTH")
e("NAV_SUPERVISOR", "BUS_EVENT", "nav olayları")
e("NAV_HEALTH", "FDIR_NAV", "NavigationHealth", S)
e("EST_SOLUTION", "EST_VEHICLE_STATE")
e("EST_VEHICLE_STATE", "BUS_STATE", "VehicleState")
# --- güdüm + görev bilgisayarı (öneri katmanı)
e("BUS_STATE", "MC_MISSION_MGR", "durum")
e("MC_PLANNER", "MC_MISSION_MGR", "rota")
e("MC_SEARCH", "MC_PLANNER", "desen")
e("MC_PERCEPTION", "MC_AI")
e("MC_AI", "MC_MAPPING")
e("MC_MAPPING", "MC_PLANNER", "harita")
e("MC_SWARM", "MC_PLANNER", "atanan görevler")
e("MC_AI", "MC_PROPOSAL", "öneri", CMD)
e("MC_MISSION_MGR", "G_WAYPOINT", "aktif hedef", CMD)
e("MC_MISSION_MGR", "MD_FSM", "nominal mod isteği", CMD)
e("G_INTENT", "G_MISSION", "niyet", CMD)
e("G_WAYPOINT", "G_MISSION", "hedef", CMD)
e("BUS_STATE", "G_MISSION", "durum")
for g in ("G_MISSION", "G_LOITER", "G_RETURN"):
    e(g, "MC_PROPOSAL", "Command", CMD)
e("MC_PROPOSAL", "CV_PROPOSAL", "CommandProposal", CMD)
e("CV_VALIDATOR", "MC_HEALTH", "red/kabul", S)
e("MC_HEALTH", "FDIR_MC", "öneri akışı", S)
# --- komut doğrulama aşamaları
e("CV_PROPOSAL", "CV_SCHEMA", "", CMD)
e("CV_SCHEMA", "CV_FRESHNESS", "", CMD)
e("CV_FRESHNESS", "CV_MODE", "", CMD)
e("CV_MODE", "CV_BOUNDS", "", CMD)
e("CV_BOUNDS", "CV_AUTHORITY", "", CMD)
e("CV_AUTHORITY", "CV_VALIDATOR", "", CMD)
e("MD_FSM", "CV_MODE", "aktif mod", S)
e("TM_CLOCK", "CV_FRESHNESS", "şimdi", S)
e("CV_VALIDATOR", "RTA_IN_ADV", "geçerli öneri", CMD)
e("CV_VALIDATOR", "FDR_CMD", "command_rejected/accepted")
# --- RTA
e("C_SAFETY", "RTA_IN_SAFE", "güvenli öneri", CMD)
e("BUS_STATE", "RTA_IN_STATE")
e("BUS_STATE", "C_SAFETY", "durum")
e("RTA_IN_STATE", "RTA_CUR_CHECK")
e("RTA_IN_STATE", "RTA_PREDICTOR")
e("RTA_IN_ADV", "RTA_PREDICTOR", "öneri")
e("RTA_PREDICTOR", "RTA_PRED_CHECK")
e("RTA_ENVELOPE", "RTA_CONSTRAINT")
e("RTA_CONSTRAINT", "RTA_PRED_CHECK", "yumuşak zarf")
e("RTA_CONSTRAINT", "RTA_CUR_CHECK", "sert zarf")
e("RTA_CUR_CHECK", "RTA_LATCH", "sert ihlal", S)
e("RTA_PRED_CHECK", "RTA_SELECTOR", "öngörülen ihlal", S)
e("RTA_LATCH", "RTA_SELECTOR", "kilit", S)
e("RTA_HYST", "RTA_SELECTOR", "geri dönüş izni", S)
e("RTA_IN_ADV", "RTA_SELECTOR", "AC", CMD)
e("RTA_IN_SAFE", "RTA_SELECTOR", "SC", CMD)
e("RTA_SELECTOR", "RTA_REASON")
e("RTA_REASON", "RTA_RECORDER")
e("RTA_RECORDER", "FDR_RTA")
e("RTA_HEALTH", "BUS_HEALTH", "RTA sağlığı", S)
e("CFG_SAFETY", "RTA_ENVELOPE", "zarflar")
e("RTA_SELECTOR", "BUS_COMMAND", "ValidatedCommand", CMD)
e("RTA_SELECTOR", "MD_CONTINGENCY", "RTA durumu", S)
e("RTA_SELECTOR", "SUP_SYSTEM", "RTA durumu", S)
# --- uçuş kontrolü -> dağıtım -> triplex -> eyleyici
e("BUS_COMMAND", "C_MODE_SEL", "ValidatedCommand", CMD)
e("MD_FSM", "C_MODE_SEL", "aktif mod", S)
e("G_TRANSITION", "C_TRANS", "geçiş programı", CMD)
e("C_MODE_SEL", "C_POS", "", CMD)
e("C_MODE_SEL", "C_VEL", "", CMD)
e("C_MODE_SEL", "C_ATT", "yatış/yunuslama", CMD)
e("C_MODE_SEL", "C_TRANS", "", CMD)
e("C_POS", "C_ATT", "eğim", CMD)
e("C_TRANS", "C_ATT", "tutum hedefi", CMD)
e("C_ATT", "AL_DEMAND", "moment", CMD)
e("C_VEL", "AL_DEMAND", "itki", CMD)
e("EN_AVAIL", "C_VEL", "güç sınırı", S)
e("AL_EFFECTIVENESS", "AL_ALLOCATOR", "B(V,σ)")
e("AL_EFFECTIVENESS", "AL_AUTHORITY")
e("AL_DEMAND", "AL_AUTHORITY", "", CMD)
e("AL_AUTHORITY", "AL_ALLOCATOR", "", CMD)
e("ACT_MOTOR_HEALTH", "AL_AUTHORITY", "sağlık vektörü", S)
e("FDIR_SURFACE_MON", "ACT_HEALTH_GATE", "yüzey sağlığı", S)
e("ACT_HEALTH_GATE", "AL_ALLOCATOR", "FAILED sütun = 0", S)
e("AL_ALLOCATOR", "AL_LIMITER", "", CMD)
e("AL_ALLOCATOR", "AL_RESIDUAL")
for lane in ("FCC_A_OUT", "FCC_B_OUT", "FCC_C_OUT"):
    e("AL_LIMITER", lane, "şerit önerisi", CMD)
    e(lane, "FCC_COMPARATOR", "", CMD)
for L in "AB":
    e(f"FCC_{L}_INPUT", f"FCC_{L}_SNAP")
    e(f"FCC_{L}_SNAP", f"FCC_{L}_GUID")
    e(f"FCC_{L}_GUID", f"FCC_{L}_CTRL", "", CMD)
    e(f"FCC_{L}_CTRL", f"FCC_{L}_OUT", "", CMD)
    e(f"FCC_{L}_HMON", "FCC_C_WATCHDOG", "kalp atışı", S)
    e("BUS_STATE", f"FCC_{L}_INPUT")
e("FCC_C_MONITOR", "FCC_COMPARATOR", "bağımsız gözlem", S)
e("SEN_IMU_C", "FCC_C_MONITOR", "IMU C")
e("FCC_C_WATCHDOG", "FCC_ISOLATION", "zaman aşımı", S)
e("FCC_C_TIMING", "FCC_ISOLATION", "zamanlama", S)
e("FCC_COMPARATOR", "FCC_C_DIVERGENCE", "fark", S)
e("FCC_C_DIVERGENCE", "FCC_ISOLATION", "kalıcı ayrışma", S)
e("FCC_COMPARATOR", "FCC_VOTER", "", CMD)
e("FCC_ISOLATION", "FCC_VOTER", "yalıtılmış şeritler", S)
e("FCC_ISOLATION", "FDIR_FCC", "şerit durumları", S)
e("TM_TIMING_MON", "FCC_C_TIMING", "", S)
e("FCC_VOTER", "ACT_CMD_MGR", "oylanmış komut", CMD)
e("ACT_CMD_MGR", "ACT_MOTOR_GROUP", "itki komutları", CMD)
e("ACT_CMD_MGR", "ACT_ELEVON_GROUP", "sapma komutları", CMD)
for m in ("M1U", "M2U", "M3U", "M4U", "M1L", "M2L", "M3L", "M4L"):
    e("ACT_MOTOR_GROUP", f"ACT_{m}", "", CMD)
for el in ("E1U", "E2U", "E1L", "E2L"):
    e("ACT_ELEVON_GROUP", f"ACT_{el}", "", CMD)
e("ACT_MOTOR_GROUP", "ACT_FEEDBACK")
e("ACT_ELEVON_GROUP", "ACT_FEEDBACK")
e("ACT_FEEDBACK", "SEN_RPM", "devir")
e("ACT_FEEDBACK", "SEN_ACT_POS", "konum")
e("ACT_FEEDBACK", "ACT_MOTOR_HEALTH")
e("AL_RESIDUAL", "ACT_SATURATION")
e("ACT_MOTOR_HEALTH", "ACT_HEALTH_GATE", "sağlık", S)
e("ACT_MOTOR_GROUP", "AV_DEP", "itki")
e("ACT_ELEVON_GROUP", "AV_AIRFRAME", "sapma")
e("AV_DEP", "DT_DYN")
e("AV_AIRFRAME", "DT_DYN")
e("AV_PARACHUTE", "DT_DYN", "sürükleme")
e("MD_FSM", "AV_PARACHUTE", "PARACHUTE modu", S)
e("DT_DYN", "AV_LANDING", "temas")
e("AV_LANDING", "BUS_EVENT", "touchdown/impact")
# --- FDIR omurgası -> araç sağlığı
e("SEN_RPM", "FDIR_MOTOR_MON", "ölçülen devir")
e("FDIR_MOTOR_MON", "ACT_MOTOR_HEALTH")
e("FDIR_MOTOR_MON", "FDIR_MOTOR", "motor durumları", S)
e("SEN_ACT_POS", "FDIR_SURFACE_MON")
e("FDIR_SURFACE_MON", "FDIR_ACTUATOR", "yüzey durumları", S)
e("AL_AUTHORITY", "FDIR_MOTOR", "hover fizibilitesi", S)
e("EN_MANAGER", "FDIR_ENERGY", "EnergyState", S)
e("EN_RESERVE", "FDIR_ENERGY", "rezerv uyarısı", S)
e("EN_BUS_HEALTH", "FDIR_ENERGY", "güç açığı", S)
e("CO_LINK_HEALTH", "FDIR_COMM", "bağlantı", S)
for did, *_ in FDIR_DOMS:
    e(f"FDIR_{did}", "FDIR_SUP", "FdirReport", S)
e("FDIR_REPORT", "FDIR_SUP", "biçim", S)
e("FDIR_SUP", "VH_MANAGER", "8 rapor", S)
e("VH_CONTROL_AUTH", "VH_MANAGER", "kontrol otoritesi", S)
e("C_ATT", "VH_CONTROL_AUTH", "controllable", S)
e("VH_MANAGER", "VH_LEVEL", "", S)
e("VH_NOT_MODELED", "VH_MANAGER", "", S)
e("VH_LEVEL", "BUS_HEALTH", "VehicleHealth", S)
e("BUS_HEALTH", "MD_CONTINGENCY", "araç sağlığı", S)
e("BUS_HEALTH", "SUP_SYSTEM", "araç sağlığı", S)
e("BUS_HEALTH", "FDR_HEALTH")
# --- enerji
e("EN_FC", "EN_SRC_HEALTH", "", S)
e("EN_BATT", "EN_SRC_HEALTH", "", S)
e("EN_SC", "EN_SRC_HEALTH", "", S)
e("EN_SOLAR", "EN_AVAIL")
for src in ("EN_FC", "EN_BATT", "EN_SC"):
    e(src, "EN_AVAIL")
e("EN_SRC_HEALTH", "EN_AVAIL", "", S)
e("EN_DEMAND", "EN_ARBITRATION")
e("EN_AVAIL", "EN_ARBITRATION")
e("EN_ARBITRATION", "EN_MANAGER", "PowerSplit")
e("EN_MANAGER", "EN_RESERVE")
e("EN_ARBITRATION", "EN_BUS_HEALTH", "", S)
e("EN_THERMAL", "EN_SRC_HEALTH", "", S)
e("MD_FSM", "EN_EMERGENCY", "acil mod", S)
e("EN_EMERGENCY", "EN_ARBITRATION", "rezerv kilidi", S)
e("EN_MANAGER", "SEN_POWER_TLM", "güç telemetrisi")
e("EN_MANAGER", "BUS_STATE", "EnergyState")
e("EN_RESERVE", "MC_MISSION_MGR", "rezerv kısıtı", S)
e("EN_RESERVE", "MD_CONTINGENCY", "eve dönüş/iniş enerjisi", S)
e("EN_RESERVE", "SUP_SYSTEM", "enerji uyarısı", S)
e("EN_MANAGER", "FDR_ENERGY")
e("ACT_MOTOR_GROUP", "EN_DEMAND", "itki -> elektrik yükü")
# --- mod + acil durum
e("MD_TABLE", "MD_FSM", "izinli geçişler", S)
e("MD_RULES", "MD_CONTINGENCY", "öncelikli kurallar", S)
e("NAV_HEALTH", "MD_CONTINGENCY", "nav bütünlüğü", S)
e("CO_LINK_HEALTH", "MD_CONTINGENCY", "C2 kesinti süresi", S)
e("AL_AUTHORITY", "MD_CONTINGENCY", "hover fizibilitesi", S)
e("MD_INPUTS", "MD_CONTINGENCY", "", S)
e("MD_CONTINGENCY", "MD_FSM", "önerilen güvenli mod", S)
e("MD_FSM", "BUS_STATE", "aktif mod")
e("MD_FSM", "FDR_MODE")
e("MD_FSM", "GUID", "mod -> güdüm seçimi", S)
e("MD_FSM", "SUP_SYSTEM", "uçuş modu", S)
# --- uçuş öncesi
for pid in ("CONFIG", "SENSOR", "NAV", "FCC", "RTA", "CTRL", "ACT", "ENERGY", "COMM", "MISSION", "REC"):
    e(f"PF_{pid}", "PRE_SUPERVISOR", "", S)
e("CFG_MANAGER", "PF_CONFIG", "", S)
e("SEN_HEALTH", "PF_SENSOR", "", S)
e("NAV_SRC_MGR", "PF_NAV", "kaynak sayısı", S)
e("FCC_C_WATCHDOG", "PF_FCC", "kalp atışları", S)
e("RTA_SELFTEST", "PF_RTA", "öz-test", S)
e("AL_AUTHORITY", "PF_CTRL", "hover marjı", S)
e("ACT_FEEDBACK", "PF_ACT", "BIT", S)
e("EN_MANAGER", "PF_ENERGY", "kullanılabilir enerji", S)
e("CO_LINK_HEALTH", "PF_COMM", "", S)
e("GCS_MISSION_PLAN", "PF_MISSION", "görev", S)
e("FDR_CORE", "PF_REC", "kayıt alınıyor", S)
e("PRE_SUPERVISOR", "MD_FSM", "preflight_ok -> ARMED", S)
# --- sistem denetimi
e("NAV_HEALTH", "SUP_SYSTEM", "nav bütünlüğü", S)
e("CO_LINK_HEALTH", "SUP_SYSTEM", "haberleşme", S)
e("FDIR_SUP", "SUP_SYSTEM", "FDIR raporları", S)
e("SUP_SYSTEM", "BUS_EVENT", "system_state_changed")
e("SUP_SYSTEM", "BUS_TLM", "sistem durumu")
# --- zaman
e("TM_CLOCK", "TM_SENSOR_TS")
e("TM_CLOCK", "TM_SCHEDULER")
e("TM_SENSOR_TS", "TM_CONSISTENCY", "", S)
e("TM_CONSISTENCY", "TM_TIMING_MON", "saat kayması", S)
e("TM_SCHEDULER", "TM_SCHED_HEALTH", "", S)
e("TM_SCHED_HEALTH", "TM_TIMING_MON", "", S)
e("TM_TIMING_MON", "EST_ESTIMATOR", "füzyon epoku", S)
# --- yapılandırma
e("CFG_SAFETY", "CFG_MANAGER")
e("CFG_VEHICLE", "CFG_MANAGER")
e("CFG_VEHICLE", "AL_EFFECTIVENESS")
e("CFG_SAFETY", "MD_CONTINGENCY", "eşikler")
e("CFG_MANAGER", "DT_PARAMS", "yapılandırma")
# --- kayıt
e("BUS_EVENT", "FDR_CORE")
e("BUS_STATE", "FDR_STATE")
e("FCC_ISOLATION", "FDR_FCC", "şerit olayları")
e("FDIR_SUP", "FDR_FDIR")
e("NAV_SUPERVISOR", "FDR_NAV")
for rid in ("STATE", "HEALTH", "MODE", "FDIR", "RTA", "NAV", "ENERGY", "CMD", "FCC"):
    e(f"FDR_{rid}", "FDR_CORE")
e("FDR_CORE", "FDR_EXPLAIN")
e("FDR_EXPLAIN", "GCS_REPLAY")
e("FDR_CORE", "DT_REPLAY", "kayıt")
# --- dijital ikiz
e("DT_SCENARIO", "DT_ENGINE")
e("DT_FAULTS", "DT_ENGINE", "arıza takvimi", S)
e("DT_MC", "DT_ENGINE", "tohumlar")
e("DT_PARAMS", "DT_DYN")
e("DT_ENV", "DT_AERO")
e("DT_AERO", "DT_DYN")
e("DT_ACTUATORS", "DT_DYN")
e("DT_ENGINE", "DT_DYN", "adım")
e("DT_DYN", "DT_SENSORS", "gerçek durum")
e("DT_DYN", "DT_NAVMODEL", "gerçek konum")
e("DT_SENSORS", "SEN_DRIVER", "simüle ölçüm")
e("DT_NAVMODEL", "SEN_GNSS_A")
e("DT_ENERGY", "EN_MANAGER", "bitki modeli")
e("DT_COMMS", "CO_GROUND", "bağlantı durumu")
e("DT_FCCMODEL", "FCC_VOTER", "şerit arızaları", S)
e("DT_FAULTS", "DT_SENSORS", "sensör arızası", S)
e("DT_FAULTS", "DT_ACTUATORS", "eyleyici arızası", S)
e("DT_FAULTS", "DT_COMMS", "bağlantı arızası", S)
e("DT_FAULTS", "DT_ENERGY", "enerji arızası", S)
e("DT_FAULTS", "DT_FCCMODEL", "şerit arızası", S)
e("DT_FAULTS", "MC_AI", "öneri arızası", S)
e("DT_ENGINE", "DT_METRICS")
e("DT_REPLAY", "DT_METRICS")
e("DT_METRICS", "GCS_REPLAY", "sonuçlar")

EDGES: tuple[Edge, ...] = tuple(_E)

# Yetki geçitleri: öneri katmanından eyleyiciye giden her komut/gözetim yolu
# bunlardan birinden geçmelidir. RTA_SELECTOR tek ValidatedCommand üreticisi,
# MD_FSM mod değişiminin tek yoludur.
AUTHORITY_GATES = frozenset({"RTA_SELECTOR", "MD_FSM"})

# ======================================================================= FAILURE CHAINS
FAILURE_CHAINS: tuple[FailureChain, ...] = (
    FailureChain("sensor_loss", "Sensor loss", "GNSS ölçümü kesilir (sensor_dropout)", "nav_source_loss",
                 ("SEN_SIGNAL_VALID", "SEN_HEALTH"), ("NAV_SRC_MGR", "FDIR_SENSOR"),
                 ("NAV_HEALTH",), ("SUP_SYSTEM",),
                 ("sensor_health_changed", "nav_source_unavailable", "vehicle_health_changed"),
                 "Kalan 3 kaynakla bütünlük korunur; görev tamamlanır"),
    FailureChain("navigation_loss", "Navigation loss", "GNSS + VIO 40 s yok", "nav_integrity_loss",
                 ("NAV_SRC_MGR", "NAV_INTEGRITY"), ("NAV_FE", "FDIR_NAV"), ("EST_INERTIAL", "NAV_HEALTH"),
                 ("MD_CONTINGENCY", "MD_FSM"),
                 ("nav_integrity_lost", "contingency", "mode_transition", "nav_integrity_restored"),
                 "LOITER_HOLD; bütünlük dönünce görev sürer"),
    FailureChain("fcc_lane_disagreement", "FCC lane disagreement", "Şerit B çıktısı sapar",
                 "fcc_lane_divergence", ("FCC_COMPARATOR", "FCC_C_DIVERGENCE"), ("FCC_ISOLATION",),
                 ("FCC_VOTER", "FDIR_FCC"), ("VH_MANAGER", "SUP_SYSTEM"),
                 ("fcc_lane_state_changed", "vehicle_health_changed"),
                 "B yalıtılır; A + C ile ikili mod; görev tamamlanır"),
    FailureChain("fcc_lane_loss", "FCC lane loss", "Şerit A kalp atışı kesilir", "fcc_lane_loss",
                 ("FCC_C_WATCHDOG",), ("FCC_ISOLATION",), ("FCC_VOTER", "FDIR_FCC"),
                 ("VH_MANAGER", "SUP_SYSTEM"), ("fcc_lane_state_changed", "vehicle_health_changed"),
                 "A FAILED; ikili mod; görev tamamlanır"),
    FailureChain("motor_degradation", "Motor degradation", "M2U %30 itki kaybı", "single_actuator_degradation",
                 ("FDIR_MOTOR_MON",), ("ACT_MOTOR_HEALTH", "FDIR_MOTOR"), ("AL_ALLOCATOR",),
                 ("VH_MANAGER", "SUP_SYSTEM"), ("fdir_warning", "vehicle_health_changed"),
                 "Sağlık ağırlıklı dağıtım; görev tamamlanır"),
    FailureChain("actuator_failure", "Actuator failure", "M1U + M1L seyirde devre dışı", "hover_capability_loss",
                 ("FDIR_MOTOR_MON",), ("FDIR_MOTOR", "ACT_HEALTH_GATE"), ("AL_AUTHORITY",),
                 ("MD_CONTINGENCY", "MD_FSM"),
                 ("fdir_failure", "actuator_excluded", "contingency", "touchdown"),
                 "Hover yok -> EMERGENCY_LAND (süzülerek)"),
    FailureChain("power_degradation", "Power degradation", "Batarya kapasitesi yarıya iner (FC yok)",
                 "energy_reserve_warning", ("EN_RESERVE",), ("FDIR_ENERGY",), ("EN_MANAGER",),
                 ("MC_MISSION_MGR", "MD_FSM"), ("energy_warning", "mission_abort", "mode_transition"),
                 "Görev iptali -> RETURN"),
    FailureChain("communication_loss", "Communication loss", "C2 kalıcı kopar", "communication_loss",
                 ("CO_HEARTBEAT",), ("CO_LINK_HEALTH", "FDIR_COMM"), ("SUP_SYSTEM",),
                 ("MD_CONTINGENCY", "MD_FSM"), ("link_lost", "contingency", "mode_transition"),
                 "30 s sonra RETURN"),
    FailureChain("mission_computer_failure", "Mission computer failure", "Öneri 6 s donar (bayat)",
                 "mission_computer_failure", ("CV_FRESHNESS",), ("CV_VALIDATOR", "FDIR_MC"),
                 ("C_SAFETY", "RTA_SELECTOR"), ("VH_MANAGER", "SUP_SYSTEM"),
                 ("command_rejected", "vehicle_health_changed", "command_accepted"),
                 "Bayat öneri RTA'ya ulaşmaz; güvenlik kontrolcüsü; akış düzelince görev sürer"),
    FailureChain("rta_intervention", "RTA intervention", "Gelişmiş kontrolcü 75° yatış önerir",
                 "rta_intervention", ("RTA_PREDICTOR", "RTA_PRED_CHECK"), ("RTA_SELECTOR",),
                 ("C_SAFETY",), ("RTA_HYST",), ("rta_intervention", "rta_recovery"),
                 "SC devralır; histerezis sonrası AC'ye dönüş; görev tamamlanır"),
)

# ======================================================================= VIEWS
VIEWS: tuple[View, ...] = (
    View("sensor-navigation", "SENSOR + NAVIGATION ARCHITECTURE", ("SEN", "AIR", "NAV", "EST")),
    View("gnc-rta", "GNC + RTA ARCHITECTURE", ("GUID", "CV", "RTA", "CTRL")),
    View("triplex-fcc", "TRIPLEX FCC ARCHITECTURE", ("FCC",)),
    View("fdir-health", "FDIR + VEHICLE HEALTH ARCHITECTURE", ("FDIR", "VH")),
    View("power", "POWER ARCHITECTURE", ("EN",)),
    View("allocation-actuators", "ACTUATOR / CONTROL ALLOCATION ARCHITECTURE", ("ALLOC", "ACT", "AV")),
    View("communication", "COMMUNICATION ARCHITECTURE", ("COMM", "GCS")),
    View("mode-supervision", "MODE / CONTINGENCY / SUPERVISION", ("MODE", "PRE", "SUP")),
    View("infrastructure", "TIME / DATA BUS / CONFIGURATION / RECORDER", ("TIME", "BUS", "CFG", "FDR")),
    View("digital-twin", "DIGITAL TWIN ARCHITECTURE", ("DT",)),
    View("mission-computer", "MISSION COMPUTER (öneri katmanı)", ("MC",)),
)

# Komut yolundaki tekil (yedeksiz) bileşenler ve azaltım notu. Denetim testi,
# komut yolundaki her yedeksiz bileşenin burada açıklanmasını ister.
SPOF_MITIGATION: tuple[tuple[str, str], ...] = (
    ("BUS_COMMAND", "Mantıksal; gerçekleştirmede şerit başına ayrı yol (planlanan)"),
    ("C_MODE_SEL", "Her FCC şeridinde koşar (simülasyonda tek hesap: ortak mod riski açık)"),
    ("C_POS", "Her FCC şeridinde koşar; simülasyonda tek hesap"),
    ("C_VEL", "Her FCC şeridinde koşar; simülasyonda tek hesap"),
    ("C_ATT", "Her FCC şeridinde koşar; simülasyonda tek hesap"),
    ("C_TRANS", "Her FCC şeridinde koşar; simülasyonda tek hesap"),
    ("C_SAFETY", "Basit ve doğrulanabilir tutulur; biçimsel doğrulama hedefi (planlanan)"),
    ("AL_DEMAND", "Şerit içinde koşar; simülasyonda tek hesap"),
    ("AL_AUTHORITY", "Şerit içinde koşar; simülasyonda tek hesap"),
    ("AL_ALLOCATOR", "Şerit içinde koşar; çıktı oylanır"),
    ("AL_LIMITER", "Şerit içinde koşar; çıktı oylanır"),
    ("FCC_COMPARATOR", "Oylama mantığı tekildir; donanımda çoğaltılmış oylayıcı planlanan"),
    ("FCC_VOTER", "Oylama mantığı tekildir; donanımda çoğaltılmış oylayıcı planlanan"),
    ("ACT_CMD_MGR", "Eyleyici başına bağımsız sürücü kanalı (planlanan)"),
    ("CV_PROPOSAL", "Durumsuz doğrulama aşaması; yanlış kabul RTA ile sınırlandırılır"),
    ("CV_SCHEMA", "Durumsuz doğrulama aşaması; yanlış kabul RTA ile sınırlandırılır"),
    ("CV_FRESHNESS", "Durumsuz doğrulama aşaması; yanlış kabul RTA ile sınırlandırılır"),
    ("CV_MODE", "Durumsuz doğrulama aşaması; yanlış kabul RTA ile sınırlandırılır"),
    ("CV_BOUNDS", "Durumsuz doğrulama aşaması; yanlış kabul RTA ile sınırlandırılır"),
    ("CV_AUTHORITY", "Durumsuz doğrulama aşaması; yanlış kabul RTA ile sınırlandırılır"),
    ("CV_VALIDATOR", "Durumsuz; red -> güvenlik kontrolcüsü (fail-safe yön)"),
    ("RTA_IN_ADV", "RTA çekirdeği küçük tutulur; DAL-B hedefi, biçimsel doğrulama planlanan"),
    ("RTA_IN_SAFE", "RTA çekirdeği küçük tutulur; DAL-B hedefi"),
    ("RTA_SELECTOR", "Tek ValidatedCommand üreticisi (bilinçli darboğaz); şerit başına RTA planlanan"),
    ("MC_PROPOSAL", "Öneri katmanı: arızası yalnızca öneri kaybıdır"),
    ("G_MISSION", "Öneri katmanı: arızası yalnızca öneri kaybıdır"),
    ("G_LOITER", "Öneri katmanı"), ("G_RETURN", "Öneri katmanı"),
    ("G_WAYPOINT", "Öneri katmanı"), ("G_INTENT", "Öneri katmanı"),
    ("MC_AI", "Öneri katmanı"), ("MC_MISSION_MGR", "Öneri katmanı"),
    ("G_TRANSITION", "İptal mantığı fail-safe yönde (askıya dönüş)"),
    ("MD_FSM", "Tek mod yetkisi (bilinçli); tablo testli"),
    ("CO_GROUND", "Tek C2 bağlantısı; kayıp kuralı + planlanan failover"),
    ("CO_MSG_VALID", "Planlanan"), ("CO_SEQ", "Planlanan"), ("CO_CMD_ROUTER", "Planlanan"),
    ("GCS_OPERATOR", "Operatör yokluğunda araç otonom güvenli davranır"),
    ("GCS_MISSION_PLAN", "Görev uçuş öncesi doğrulanır"),
    ("MC_PLANNER", "Öneri katmanı"), ("MC_SEARCH", "Öneri katmanı"), ("MC_PERCEPTION", "Öneri katmanı"),
    ("MC_MAPPING", "Öneri katmanı"), ("MC_SWARM", "Öneri katmanı"),
    ("CO_V2V", "Öneri katmanı girdisi"),
)

ARCHITECTURE = Architecture(GROUPS, COMPONENTS, EDGES, AUTHORITY_GATES, FAILURE_CHAINS, VIEWS,
                            SPOF_MITIGATION)
