"""SİMURG alan hataları.

Hiyerarşi kasıtlı olarak sığ tutulmuştur: tüm paket hataları `SimurgError`
altında toplanır, böylece çağıran taraf genel `except Exception` yerine
yalnızca beklenen alan hatalarını yakalayabilir.
"""

from __future__ import annotations


class SimurgError(Exception):
    """Tüm SİMURG alan hatalarının tabanı."""


class ConfigurationError(SimurgError, ValueError):
    """Geçersiz ya da tutarsız yapılandırma."""


class InvalidScenarioError(SimurgError, ValueError):
    """Senaryo tanımı geçersiz (bilinmeyen hedef, negatif süre vb.)."""


class SimulationError(SimurgError, RuntimeError):
    """Simülasyon sırasında sayısal ya da mantıksal tutarsızlık."""
