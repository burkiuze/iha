"""SİMURG sistem mimarisinin makine-okunur kaydı ve belge üreticisi.

    from simurg.architecture import ARCHITECTURE
    python -m simurg.architecture --update docs/15-sistem-mimarisi.md
    python -m simurg.architecture --check  docs/15-sistem-mimarisi.md
"""

from .model import Architecture, Component, Edge, EdgeKind, Group, Status
from .registry import ARCHITECTURE

__all__ = ["ARCHITECTURE", "Architecture", "Component", "Edge", "EdgeKind", "Group", "Status"]
