"""SİMURG sistem mimarisinin makine-okunur kaydı ve belge üreticisi.

    from simurg.architecture import ARCHITECTURE
    python -m simurg.architecture --update-all     # docs/15 + docs/mimari/*.md
    python -m simurg.architecture --check-all
"""

from .model import (Architecture, Component, Edge, EdgeKind, FailureChain, Group, Status,
                    View)
from .registry import ARCHITECTURE

__all__ = ["ARCHITECTURE", "Architecture", "Component", "Edge", "EdgeKind", "FailureChain",
           "Group", "Status", "View"]
