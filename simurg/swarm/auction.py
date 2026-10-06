"""Enerji farkındalıklı, çatışmasız sürü görev dağıtımı.

CBBA (Consensus-Based Bundle Algorithm) ailesinin deterministik,
merkezi-eşdeğer bir referans modelidir. Her görevin ödülü, ona ulaşma
zamanıyla üstel olarak azalır (zaman indirgemeli ödül):

    ödül(görev) = öncelik * exp(-varış_zamanı / tau)

Her turda her ajan, her atanmamış görevi rotasının her konumuna eklemeyi
dener; marjinal skor = yeni rotanın toplam ödülü - eski rotanın toplam
ödülü (ekleme sonraki görevleri geciktirdiği için bu değer cezayı da içerir).
Global en yüksek teklif kazanır. Zaman indirgemesi, yükün doğal olarak
ajanlara yayılmasını sağlar: dolu bir ajanın rotasına eklenen görev geç
ulaşılacağı için daha az değerlidir.
Dağıtık uygulamada aynı sonuca, ağ üzerinden kazanan-teklif tablolarının
uzlaşı ile senkronize edilmesiyle ulaşılır (bkz. docs/09-suru-ve-isbirligi.md).

Fizibilite: rota + görev süreleri + üsse dönüş enerjisi, ajanın kullanılabilir
enerjisinin (1 - rezerv) kısmını aşamaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Agent:
    id: str
    pos: np.ndarray
    energy_wh: float
    speed_mps: float = 28.0
    cruise_w: float = 590.0
    reserve: float = 0.25
    route: list[str] = field(default_factory=list)


@dataclass
class Task:
    id: str
    pos: np.ndarray
    duration_s: float = 120.0
    priority: float = 1.0


def route_energy_wh(agent: Agent, route: list[Task], base: np.ndarray) -> float:
    pts = [agent.pos] + [t.pos for t in route] + [base]
    dist = sum(float(np.linalg.norm(b - a)) for a, b in zip(pts, pts[1:]))
    t_s = dist / agent.speed_mps + sum(t.duration_s for t in route)
    return agent.cruise_w * t_s / 3600.0


def route_reward(agent: Agent, route: list[Task], tau_s: float) -> float:
    t, pos, total = 0.0, agent.pos, 0.0
    for task in route:
        t += float(np.linalg.norm(task.pos - pos)) / agent.speed_mps
        total += task.priority * float(np.exp(-t / tau_s))
        t += task.duration_s
        pos = task.pos
    return total


def allocate(agents: list[Agent], tasks: list[Task], base,
             tau_s: float = 3600.0) -> dict[str, list[str]]:
    base = np.asarray(base, float)
    by_id = {t.id: t for t in tasks}
    routes: dict[str, list[Task]] = {a.id: [] for a in agents}
    unassigned = sorted(by_id)

    while unassigned:
        best = None   # (score, agent_id, task_id, insert_pos)
        for a in sorted(agents, key=lambda a: a.id):
            r = routes[a.id]
            s0 = route_reward(a, r, tau_s)
            budget = a.energy_wh * (1.0 - a.reserve)
            for tid in unassigned:
                t = by_id[tid]
                for k in range(len(r) + 1):
                    cand = r[:k] + [t] + r[k:]
                    e = route_energy_wh(a, cand, base)
                    if e > budget:
                        continue
                    score = route_reward(a, cand, tau_s) - s0
                    if best is None or score > best[0] + 1e-12:
                        best = (score, a.id, tid, k)
        if best is None:
            break
        _, aid, tid, k = best
        routes[aid].insert(k, by_id[tid])
        unassigned.remove(tid)

    for a in agents:
        a.route = [t.id for t in routes[a.id]]
    return {aid: [t.id for t in r] for aid, r in routes.items()}
