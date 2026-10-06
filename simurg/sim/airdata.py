"""Hava verisi (pitot + barometre) ve açık geri dönüş politikası.

Ölçüm geçersizse sessizce eski değer KULLANILMAZ: açık bir geri dönüş
kaynağı seçilir ve durum değişimi olay olarak bildirilir.

  hava hızı yok -> yer hızı tabanlı kestirim (rüzgâr bilinmiyor, bozulmuş)
  irtifa yok    -> son ölçüm + ataletsel dikey hız entegrasyonu (bozulmuş)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .sensors import SensorModel


@dataclass(frozen=True)
class AirDataChange:
    sensor_id: str
    degraded: bool
    fallback: str


class AirDataSystem:
    def __init__(self, pitot: SensorModel, baro: SensorModel) -> None:
        self.pitot, self.baro = pitot, baro
        self.airspeed_mps = 0.0
        self.altitude_m = 0.0
        self.degraded: dict[str, bool] = {pitot.sensor_id: False, baro.sensor_id: False}

    def update(self, t: float, dt: float, airspeed_true: float, altitude_true: float,
               vel_ned: np.ndarray) -> list[AirDataChange]:
        changes = []
        a = self.pitot.measure(airspeed_true, t)
        if a.valid and np.all(np.isfinite(a.value)):
            self.airspeed_mps = max(float(a.value[0]), 0.0)
            changes += self._mark(self.pitot.sensor_id, False, "")
        else:
            self.airspeed_mps = float(np.linalg.norm(vel_ned))
            changes += self._mark(self.pitot.sensor_id, True, "yer_hizi_kestirimi")
        b = self.baro.measure(altitude_true, t)
        if b.valid and np.all(np.isfinite(b.value)):
            self.altitude_m = float(b.value[0])
            changes += self._mark(self.baro.sensor_id, False, "")
        else:
            self.altitude_m += -float(vel_ned[2]) * dt
            changes += self._mark(self.baro.sensor_id, True, "ataletsel_dikey_entegrasyon")
        return changes

    def _mark(self, sid: str, degraded: bool, fallback: str) -> list[AirDataChange]:
        if self.degraded[sid] == degraded:
            return []
        self.degraded[sid] = degraded
        return [AirDataChange(sid, degraded, fallback)]
