"""GNSS'ten bağımsız, çok kaynaklı konum füzyonu ve bütünlük izleme.

Kaynaklar (örnek): GNSS, görsel-ataletsel odometri (VIO), arazi referanslı
navigasyon (TRN), manyetik anomali navigasyonu (MagNav), yıldız/güneş
takipçisi destekli ataletsel çözüm. Her kaynak bir konum ve kovaryans verir.

Algoritma (RAIM benzeri, "çözüm ayrıştırma" yaklaşımı):
  1. Ters-kovaryans ağırlıklı füzyon.
  2. Ki-kare tutarlılık testi: T = sum (z_i - x)^T R_i^-1 (z_i - x),
     serbestlik derecesi (m-1)*d.
  3. T eşiği aşarsa her kaynağı sırayla dışarıda bırak (leave-one-out);
     kalan kümede T'yi en çok düşüren dışlamayı kabul et. Tutarlı küme
     bulunana ya da 2 kaynak kalana dek tekrar et.
  4. Koruma seviyesi (protection level): PL = k_md * sqrt(lambda_max(P)).

Bu yaklaşım GNSS sahteciliğini (spoofing) "GNSS'e güvenmeme" yerine
"hiçbir kaynağa koşulsuz güvenmeme" ilkesiyle ele alır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import NormalDist

import numpy as np


def chi2_quantile(p: float, dof: int) -> float:
    """Wilson–Hilferty yaklaşımıyla ki-kare dağılımı ters CDF'i."""
    z = NormalDist().inv_cdf(p)
    k = float(dof)
    return k * (1.0 - 2.0 / (9.0 * k) + z * np.sqrt(2.0 / (9.0 * k))) ** 3


@dataclass
class PositionFix:
    source: str
    pos: np.ndarray        # (d,)
    cov: np.ndarray        # (d, d)


@dataclass
class IntegrityResult:
    position: np.ndarray
    covariance: np.ndarray
    used: list[str]
    excluded: list[str]
    test_statistic: float
    threshold: float
    protection_level_m: float
    integrity_ok: bool
    # Dışlamadan ÖNCEKİ tüm-kaynak testi (dışlamayı tetikleyen değerler)
    initial_test_statistic: float = float("nan")
    initial_threshold: float = float("nan")


def fuse(fixes: list[PositionFix]) -> tuple[np.ndarray, np.ndarray]:
    info = sum(np.linalg.inv(f.cov) for f in fixes)
    P = np.linalg.inv(info)
    x = P @ sum(np.linalg.inv(f.cov) @ f.pos for f in fixes)
    return x, P


def test_statistic(fixes: list[PositionFix], x: np.ndarray) -> float:
    return float(sum((f.pos - x) @ np.linalg.inv(f.cov) @ (f.pos - x) for f in fixes))


@dataclass
class IntegrityMonitor:
    p_false_alarm: float = 1e-5
    p_missed_detection: float = 1e-7
    alert_limit_m: float = 50.0
    min_sources: int = 2
    log: list[str] = field(default_factory=list)

    def _threshold(self, m: int, d: int) -> float:
        dof = max((m - 1) * d, 1)
        return chi2_quantile(1.0 - self.p_false_alarm, dof)

    def evaluate(self, fixes: list[PositionFix]) -> IntegrityResult:
        if not fixes:
            raise ValueError("konum kaynağı yok")
        d = fixes[0].pos.size
        active = list(fixes)
        excluded: list[str] = []

        x, P = fuse(active)
        T = test_statistic(active, x)
        thr = self._threshold(len(active), d)
        T0, thr0 = T, thr

        while T > thr and len(active) > self.min_sources:
            best = None
            for i in range(len(active)):
                subset = active[:i] + active[i + 1:]
                xs, _ = fuse(subset)
                ts = test_statistic(subset, xs) / self._threshold(len(subset), d)
                if best is None or ts < best[0]:
                    best = (ts, i)
            bad = active.pop(best[1])
            excluded.append(bad.source)
            self.log.append(f"dislandi:{bad.source}")
            x, P = fuse(active)
            T = test_statistic(active, x)
            thr = self._threshold(len(active), d)

        k_md = NormalDist().inv_cdf(1.0 - self.p_missed_detection / 2.0)
        pl = float(k_md * np.sqrt(np.max(np.linalg.eigvalsh(P))))
        consistent = T <= thr or len(active) == 1
        ok = consistent and pl <= self.alert_limit_m
        return IntegrityResult(x, P, [f.source for f in active], excluded,
                               T, thr, pl, ok, T0, thr0)
