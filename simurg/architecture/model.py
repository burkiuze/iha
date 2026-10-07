"""Mimari bileşen kaydının veri modeli."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    IMPLEMENTED = "IMPLEMENTED"   # kodda var, simülasyona bağlı, otomatik testle doğrulanmış
    PARTIAL = "PARTIAL"           # basitleştirilmiş / kısmen modellenmiş / simülasyona bağlı değil
    UNVALIDATED = "UNVALIDATED"   # kodda var ama bu davranışı doğrulayan otomatik test/senaryo yok
    PLANNED = "PLANNED"           # yalnızca mimaride; kod yok


CODE_BACKED = frozenset({Status.IMPLEMENTED, Status.PARTIAL, Status.UNVALIDATED})


class EdgeKind(str, Enum):
    DATA = "data"                 # ölçüm / durum akışı
    COMMAND = "command"           # komut / öneri akışı
    SUPERVISORY = "supervisory"   # sağlık, mod, karar, izleme (çapraz)


@dataclass(frozen=True)
class Group:
    id: str
    title: str
    subgroups: tuple[tuple[str, str], ...] = ()   # (id, başlık)


@dataclass(frozen=True)
class Component:
    id: str
    name: str
    group: str
    responsibility: str
    inputs: str
    outputs: str
    health: str                         # sağlık durumu kümesi / nasıl raporlanır
    status: Status
    code: tuple[str, ...] = ()          # "yol::Sembol"
    sub: str = ""
    proposal_only: bool = False         # YZ/öneri katmanı: eyleyici yetkisi yok
    note: str = ""
    failure: str = ""                   # arıza davranışı (Failure Behaviour)
    master: bool = False                # ana (master) diyagramda gösterilir
    redundancy: str = ""                # yedeklilik (boş: tekil örnek)


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    label: str = ""
    kind: EdgeKind = EdgeKind.DATA


@dataclass(frozen=True)
class FailureChain:
    """Arıza -> tespit -> yalıtım -> bozulmuş çalışma -> acil durum -> olay/kayıt.

    Aşamalar bileşen kimlikleridir; `events` kayıtta görülmesi gereken olay
    türleridir ve `scenario` adlı kütüphane senaryosunda testle doğrulanır.
    """
    id: str
    title: str
    fault: str
    scenario: str
    detection: tuple[str, ...]
    isolation: tuple[str, ...]
    degradation: tuple[str, ...]
    contingency: tuple[str, ...]
    events: tuple[str, ...]
    outcome: str


@dataclass(frozen=True)
class View:
    """Belge görünümü: bir doküman bölümünde birlikte çizilen gruplar."""
    id: str
    title: str
    groups: tuple[str, ...]


@dataclass(frozen=True)
class Architecture:
    groups: tuple[Group, ...]
    components: tuple[Component, ...]
    edges: tuple[Edge, ...]
    gates: frozenset[str] = field(default_factory=frozenset)   # yetki geçitleri
    failure_chains: tuple[FailureChain, ...] = ()
    views: tuple[View, ...] = ()
    spof_mitigation: tuple[tuple[str, str], ...] = ()

    def by_id(self) -> dict[str, Component]:
        return {c.id: c for c in self.components}
