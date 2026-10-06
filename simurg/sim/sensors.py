"""Simüle sensör modelleri (marka/model bağımsız).

Her sensör kendi açık `numpy.random.Generator` nesnesini kullanır; küresel
rastgele durum yoktur. Ölçüm modeli:

    z = h(x) * (1 if sağlıklı) + bias + noise_scale * N(0, σ²)
    geçersiz (dropout)  -> valid=False

Raporlanan kovaryans sensörün NOMİNAL beyanıdır; sensör kendi biasından
habersizdir (bütünlük izleme bu yüzden gereklidir).
"""

from __future__ import annotations

import numpy as np

from ..core.errors import InvalidScenarioError
from ..core.types import SensorMeasurement
from .faults import Fault, FaultKind


class SensorModel:
    def __init__(self, sensor_id: str, noise_std: np.ndarray | float,
                 rng: np.random.Generator) -> None:
        self.sensor_id = sensor_id
        self.noise_std = np.atleast_1d(np.asarray(noise_std, float))
        self.rng = rng
        self.bias = np.zeros_like(self.noise_std)
        self.noise_scale = 1.0
        self.dropout = False
        self.health = 1.0

    def measure(self, truth: np.ndarray | float, t: float) -> SensorMeasurement:
        truth = np.atleast_1d(np.asarray(truth, float))
        # Gürültü her çağrıda üretilir (dropout'ta bile): RNG akışı arızadan bağımsız kalır.
        noise = self.rng.standard_normal(truth.shape) * self.noise_std * self.noise_scale
        cov = np.diag(self.noise_std ** 2)
        if self.dropout:
            return SensorMeasurement(self.sensor_id, t, truth * np.nan, cov, False, 0.0, 0.0)
        quality = 1.0 / self.noise_scale
        return SensorMeasurement(self.sensor_id, t, truth + self.bias + noise, cov, True,
                                 float(min(quality, 1.0)), self.health)

    # ---- FaultTarget --------------------------------------------------------
    def apply_fault(self, fault: Fault) -> None:
        if fault.kind is FaultKind.SENSOR_DROPOUT:
            self.dropout, self.health = True, 0.0
        elif fault.kind is FaultKind.SENSOR_BIAS:
            b = fault.params.get("bias")
            self.bias = (np.asarray(b, float) if b is not None
                         else self.noise_std * 30.0 * fault.severity)
            self.health = 1.0 - fault.severity
        elif fault.kind is FaultKind.SENSOR_NOISE:
            self.noise_scale = 1.0 + 9.0 * fault.severity
            self.health = 1.0 - 0.5 * fault.severity
        else:
            raise InvalidScenarioError(f"sensör bu arızayı desteklemiyor: {fault.kind}")

    def clear_fault(self, fault: Fault) -> None:
        if fault.kind is FaultKind.SENSOR_DROPOUT:
            self.dropout = False
        elif fault.kind is FaultKind.SENSOR_BIAS:
            self.bias = np.zeros_like(self.noise_std)
        elif fault.kind is FaultKind.SENSOR_NOISE:
            self.noise_scale = 1.0
        self.health = 1.0


class SensorSuite:
    """Sensörleri kimlikleriyle tutar; arıza hedefi olarak sensör:<id> çözer."""

    def __init__(self, sensors: list[SensorModel]) -> None:
        self.sensors = {s.sensor_id: s for s in sensors}

    def __getitem__(self, key: str) -> SensorModel:
        return self.sensors[key]

    def _get(self, fault: Fault) -> SensorModel:
        try:
            return self.sensors[fault.component]
        except KeyError:
            raise InvalidScenarioError(f"bilinmeyen sensör: {fault.component}") from None

    def apply_fault(self, fault: Fault) -> None:
        self._get(fault).apply_fault(fault)

    def clear_fault(self, fault: Fault) -> None:
        self._get(fault).clear_fault(fault)


class SimulatedPositionProvider:
    """Bir konum sensörünü `nav.providers.NavigationProvider` arayüzüne bağlar."""

    def __init__(self, sensor: SensorModel, truth_fn) -> None:
        self.sensor = sensor
        self.source_id = sensor.sensor_id
        self._truth = truth_fn

    def provide(self, t: float) -> SensorMeasurement:
        return self.sensor.measure(self._truth(), t)


# Varsayılan konum kaynakları ve 1σ (m) — docs/07-navigasyon.md ile uyumlu.
DEFAULT_POSITION_SOURCES: dict[str, float] = {
    "GNSS": 3.0, "VIO": 8.0, "TRN": 15.0, "MAGNAV": 25.0,
}
