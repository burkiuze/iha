"""Katsayı tabloları için doğrusal ara değerleme (yalnızca NumPy).

CFD, rüzgâr tüneli ya da uçuş testinden gelecek tabloların yükleneceği yer
burasıdır. Tablo sınırları dışında değer kırpılır (extrapolation yapılmaz);
çağıran taraf `in_range` ile tablo kapsamını denetleyebilir.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core.errors import ConfigurationError


@dataclass(frozen=True)
class Table1D:
    x: np.ndarray
    y: np.ndarray

    def __post_init__(self) -> None:
        x, y = np.asarray(self.x, float), np.asarray(self.y, float)
        if x.ndim != 1 or x.shape != y.shape or x.size < 2:
            raise ConfigurationError("Table1D: x ve y aynı boyutlu 1-B dizi olmalı (>=2)")
        if np.any(np.diff(x) <= 0):
            raise ConfigurationError("Table1D: x kesin artan olmalı")
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)

    def __call__(self, xq: float) -> float:
        return float(np.interp(xq, self.x, self.y))

    def in_range(self, xq: float) -> bool:
        return bool(self.x[0] <= xq <= self.x[-1])


@dataclass(frozen=True)
class Table2D:
    """z[i, j] = f(x[i], y[j]) için çift doğrusal ara değerleme."""
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray

    def __post_init__(self) -> None:
        x, y, z = (np.asarray(a, float) for a in (self.x, self.y, self.z))
        if z.shape != (x.size, y.size):
            raise ConfigurationError("Table2D: z boyutu (len(x), len(y)) olmalı")
        if np.any(np.diff(x) <= 0) or np.any(np.diff(y) <= 0):
            raise ConfigurationError("Table2D: eksenler kesin artan olmalı")
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)
        object.__setattr__(self, "z", z)

    def __call__(self, xq: float, yq: float) -> float:
        xq = float(np.clip(xq, self.x[0], self.x[-1]))
        yq = float(np.clip(yq, self.y[0], self.y[-1]))
        i = int(np.clip(np.searchsorted(self.x, xq) - 1, 0, self.x.size - 2))
        j = int(np.clip(np.searchsorted(self.y, yq) - 1, 0, self.y.size - 2))
        tx = (xq - self.x[i]) / (self.x[i + 1] - self.x[i])
        ty = (yq - self.y[j]) / (self.y[j + 1] - self.y[j])
        z = self.z
        return float((1 - tx) * (1 - ty) * z[i, j] + tx * (1 - ty) * z[i + 1, j]
                     + (1 - tx) * ty * z[i, j + 1] + tx * ty * z[i + 1, j + 1])
