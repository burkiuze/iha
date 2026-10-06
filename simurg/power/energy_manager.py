"""Üç kaynaklı hibrit güç yönetimi: PEM yakıt hücresi + Li-ion + süperkapasitör
(+ kanat üstü ince film güneş paneli).

Frekans ayrıştırmalı strateji:
  * Güneş   : her zaman önce kullanılır (sıfır marjinal maliyet).
  * Yakıt hücresi: talebin alçak frekanslı bileşenini izler, eğim (slew)
                sınırlıdır; batarya SoC'sini hedefte tutmak için bir
                düzeltme terimi alır. Hızlı yük değişimi PEM membranını
                yıpratır; bu yüzden asla doğrudan hızlı talebi izlemez.
  * Batarya : orta frekans; kendi eğim sınırı vardır.
  * Süperkap: yüksek frekans / anlık tepe (rüzgâr hamlesi, motor arızası
                sonrası ani itki artışı). Sakin anlarda bataryadan yavaşça
                yeniden şarj edilir.

Tüm güçler DC bara (bus) tarafında, watt cinsindendir; pozitif = baraya
güç verir (deşarj), negatif = baradan güç çeker (şarj).
"""

from __future__ import annotations

from dataclasses import dataclass, field

H2_LHV_WH_PER_KG = 33_330.0


@dataclass
class PowerConfig:
    fc_max_w: float = 800.0
    fc_slew_w_per_s: float = 60.0
    fc_filter_tau_s: float = 20.0
    h2_mass_kg: float = 0.139               # 6.8 L, 300 bar
    batt_capacity_wh: float = 389.0         # 12S2P 21700
    batt_max_discharge_w: float = 3_600.0
    batt_max_charge_w: float = 600.0
    batt_slew_w_per_s: float = 4_000.0
    batt_efficiency: float = 0.97
    batt_soc_target: float = 0.80
    batt_soc_reserve: float = 0.20          # eve dönüş rezervi, sadece acil durumda
    soc_gain_w: float = 1_500.0             # SoC hatası başına FC düzeltmesi
    sc_capacity_wh: float = 6.0
    sc_max_w: float = 2_500.0
    sc_soc_target: float = 0.80
    sc_recharge_w: float = 150.0


def fc_efficiency(p_w: float, p_max_w: float) -> float:
    """PEM verimi düşük yükte yüksek, tam yükte düşüktür (basit doğrusal model)."""
    if p_w <= 0:
        return 0.55
    return 0.55 - 0.15 * min(p_w / p_max_w, 1.0)


@dataclass
class PowerSplit:
    load_w: float
    solar_w: float
    fc_w: float
    batt_w: float
    sc_w: float
    curtailed_w: float
    unmet_w: float

    @property
    def bus_balance_w(self) -> float:
        """Kaynaklar - yük; sıfır olmalıdır (karşılanamayan dahil)."""
        return (self.solar_w - self.curtailed_w + self.fc_w + self.batt_w
                + self.sc_w + self.unmet_w - self.load_w)


@dataclass
class EnergyManager:
    cfg: PowerConfig = field(default_factory=PowerConfig)

    def __post_init__(self):
        c = self.cfg
        self.batt_soc = c.batt_soc_target
        self.sc_soc = c.sc_soc_target
        self.h2_wh = c.h2_mass_kg * H2_LHV_WH_PER_KG   # kimyasal enerji
        self.fc_w = 0.0
        self.batt_w = 0.0
        self._demand_lp = 0.0

    # ---- yardımcılar -------------------------------------------------
    def _batt_limits(self, dt: float, allow_reserve: bool) -> tuple[float, float]:
        c = self.cfg
        floor = 0.0 if allow_reserve else c.batt_soc_reserve
        e_avail = max(self.batt_soc - floor, 0.0) * c.batt_capacity_wh
        e_room = max(1.0 - self.batt_soc, 0.0) * c.batt_capacity_wh
        p_dis = min(c.batt_max_discharge_w, e_avail * 3600.0 / dt * c.batt_efficiency)
        p_chg = min(c.batt_max_charge_w, e_room * 3600.0 / dt / c.batt_efficiency)
        return -p_chg, p_dis

    def _sc_limits(self, dt: float) -> tuple[float, float]:
        c = self.cfg
        e = self.sc_soc * c.sc_capacity_wh
        room = (1.0 - self.sc_soc) * c.sc_capacity_wh
        return (-min(c.sc_max_w, room * 3600.0 / dt),
                min(c.sc_max_w, e * 3600.0 / dt))

    # ---- ana adım ------------------------------------------------------
    def step(self, dt: float, load_w: float, solar_w: float = 0.0,
             emergency: bool = False) -> PowerSplit:
        c = self.cfg
        net = load_w - solar_w
        curtailed = 0.0

        # 1) Yakıt hücresi: filtrelenmiş talep + SoC düzeltmesi, eğim sınırlı
        a = dt / (c.fc_filter_tau_s + dt)
        self._demand_lp += a * (net - self._demand_lp)
        fc_target = self._demand_lp + c.soc_gain_w * (c.batt_soc_target - self.batt_soc)
        fc_target = min(max(fc_target, 0.0), c.fc_max_w)
        if self.h2_wh <= 0.0:
            fc_target = 0.0
        step_lim = c.fc_slew_w_per_s * dt
        self.fc_w += min(max(fc_target - self.fc_w, -step_lim), step_lim)
        fc = self.fc_w

        # 2) Kalan: batarya (eğim sınırlı) + süperkap (hızlı bileşen)
        remainder = net - fc
        b_lo, b_hi = self._batt_limits(dt, emergency)
        s_lo, s_hi = self._sc_limits(dt)
        bstep = c.batt_slew_w_per_s * dt
        batt = min(max(remainder, self.batt_w - bstep), self.batt_w + bstep)
        batt = min(max(batt, b_lo), b_hi)
        sc = min(max(remainder - batt, s_lo), s_hi)
        # süperkap doyduysa batarya eğim sınırını aşarak devralır
        batt = min(max(remainder - sc, b_lo), b_hi)
        leftover = remainder - batt - sc
        unmet = max(leftover, 0.0)          # pozitif: yük karşılanamadı
        curtailed = max(-leftover, 0.0)     # negatif: güneş/FC fazlası atılır

        # 3) Süperkap sakin anda bataryadan geri şarj
        if self.sc_soc < c.sc_soc_target and unmet == 0.0:
            xfer = min(c.sc_recharge_w, b_hi - batt, sc - s_lo)
            if xfer > 0:
                batt += xfer
                sc -= xfer

        # 4) Durum güncelle
        hrs = dt / 3600.0
        if batt >= 0:
            self.batt_soc -= batt / c.batt_efficiency * hrs / c.batt_capacity_wh
        else:
            self.batt_soc -= batt * c.batt_efficiency * hrs / c.batt_capacity_wh
        self.sc_soc -= sc * hrs / c.sc_capacity_wh
        if fc > 0:
            self.h2_wh = max(self.h2_wh - fc / fc_efficiency(fc, c.fc_max_w) * hrs, 0.0)
        self.batt_w = batt
        self.batt_soc = min(max(self.batt_soc, 0.0), 1.0)
        self.sc_soc = min(max(self.sc_soc, 0.0), 1.0)

        return PowerSplit(load_w, solar_w, fc, batt, sc, curtailed, unmet)

    # ---- görev seviyesi sorgular --------------------------------------
    def usable_energy_wh(self, include_reserve: bool = False) -> float:
        c = self.cfg
        floor = 0.0 if include_reserve else c.batt_soc_reserve
        batt = max(self.batt_soc - floor, 0.0) * c.batt_capacity_wh * c.batt_efficiency
        fc = self.h2_wh * fc_efficiency(c.fc_max_w * 0.7, c.fc_max_w)
        return batt + fc

    def return_home_feasible(self, distance_m: float, groundspeed_mps: float,
                             cruise_power_w: float, landing_energy_wh: float = 60.0,
                             margin: float = 1.3) -> bool:
        """Eve dönüş + VTOL iniş enerjisi, güvenlik payıyla karşılanabiliyor mu?

        Rezerv (batt_soc_reserve) bu hesaba dahil EDİLMEZ; o, öngörülemeyen
        durumlar için ayrılmış son katmandır.
        """
        if groundspeed_mps <= 0:
            return False
        t_h = distance_m / groundspeed_mps / 3600.0
        need = (cruise_power_w * t_h + landing_energy_wh) * margin
        return self.usable_energy_wh() >= need
