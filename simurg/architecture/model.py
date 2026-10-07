"""Mimari bileşen kaydının veri modeli."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    IMPLEMENTED = "IMPLEMENTED"   # kodda var, simülasyona bağlı, testli
    PARTIAL = "PARTIAL"           # kısmi / basitleştirilmiş ya da simülasyona bağlı değil
    PLANNED = "PLANNED"           # yalnızca mimaride; kod yok


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
    health: str
    status: Status
    code: tuple[str, ...] = ()          # "yol::Sembol"
    sub: str = ""
    proposal_only: bool = False         # YZ/öneri katmanı: eyleyici yetkisi yok
    note: str = ""


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    label: str = ""
    kind: EdgeKind = EdgeKind.DATA


@dataclass(frozen=True)
class Architecture:
    groups: tuple[Group, ...]
    components: tuple[Component, ...]
    edges: tuple[Edge, ...]
    gates: frozenset[str] = field(default_factory=frozenset)   # yetki geçitleri

    def by_id(self) -> dict[str, Component]:
        return {c.id: c for c in self.components}
