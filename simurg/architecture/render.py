"""Kayıttan Mermaid diyagramları ve Markdown tabloları üretir (deterministik)."""

from __future__ import annotations

from collections import Counter

from . import audit
from .model import Architecture, Component, Edge, EdgeKind, Status, View

_ARROW = {EdgeKind.DATA: "-->", EdgeKind.COMMAND: "==>", EdgeKind.SUPERVISORY: "-.->"}
_CLASSDEF = (
    "classDef implemented fill:#d7f5dd,stroke:#1a7f37,color:#0b3d1a;",
    "classDef partial fill:#fff4c2,stroke:#9a6700,color:#3d2e00;",
    "classDef unvalidated fill:#ffe1c7,stroke:#bc4c00,color:#4d1f00;",
    "classDef planned fill:#eef0f3,stroke:#8c959f,color:#57606a,stroke-dasharray: 4 3;",
    "classDef gate fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a,stroke-width:3px;",
    "classDef ext fill:#ffffff,stroke:#8c959f,color:#57606a;",
    "classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;",
)
_KIND_RANK = {EdgeKind.DATA: 0, EdgeKind.SUPERVISORY: 1, EdgeKind.COMMAND: 2}
_STATUS_ORDER = (Status.IMPLEMENTED, Status.PARTIAL, Status.UNVALIDATED, Status.PLANNED)


def _label(text: str) -> str:
    return text.replace('"', "'")


def _node(c: Component, gates: frozenset[str]) -> str:
    cls = "gate" if c.id in gates else c.status.value.lower()
    return f'{c.id}["{_label(c.name)}"]:::{cls}'


def container_ids(a: Architecture) -> dict[str, str]:
    """Grup ve alt grup kimliği -> başlık."""
    out = {}
    for g in a.groups:
        out[g.id] = g.title
        for sid, title in g.subgroups:
            out[sid] = title
    return out


def members(a: Architecture, container: str) -> list[str]:
    return audit.members(a, container)


def top_group(a: Architecture, node: str) -> str:
    by_id = a.by_id()
    if node in by_id:
        return by_id[node].group
    for g in a.groups:
        if node == g.id or node in {sid for sid, _ in g.subgroups}:
            return g.id
    raise KeyError(node)


def _edge(e: Edge, labels: bool) -> str:
    arrow = _ARROW[e.kind]
    if labels and e.label:
        return f'{e.src} {arrow}|"{_label(e.label)}"| {e.dst}'
    return f"{e.src} {arrow} {e.dst}"


def _group_block(a: Architecture, gid: str, only: set[str] | None = None,
                 indent: str = "  ") -> list[str]:
    g = next(x for x in a.groups if x.id == gid)
    pick = [c for c in a.components if c.group == gid and (only is None or c.id in only)]
    if not pick:
        return []
    lines = [f'{indent}subgraph {g.id}["{_label(g.title)}"]', f"{indent}  direction TB"]
    for sid, title in g.subgroups:
        nodes = [c for c in pick if c.sub == sid]
        if not nodes:
            continue
        lines.append(f'{indent}  subgraph {sid}["{_label(title)}"]')
        lines += [f"{indent}    {_node(c, a.gates)}" for c in nodes]
        lines.append(f"{indent}  end")
    lines += [f"{indent}  {_node(c, a.gates)}" for c in pick if not c.sub]
    lines.append(f"{indent}end")
    return lines


# ------------------------------------------------------------------ master
def projected_edges(a: Architecture, keep: set[str]) -> list[tuple[str, str, EdgeKind]]:
    """Yalnızca `keep` düğümleri arasında kenar: aradaki gizli düğümlerden geçen
    yollar en baskın kenar türüyle doğrudan bağa indirgenir."""
    out_edges: dict[str, list[tuple[str, EdgeKind]]] = {c.id: [] for c in a.components}
    for e in a.edges:
        for s in audit.expand(a, e.src):
            for d in audit.expand(a, e.dst):
                out_edges[s].append((d, e.kind))
    found: dict[tuple[str, str], EdgeKind] = {}
    for src in sorted(keep):
        stack = [(d, k, 1) for d, k in out_edges[src]]
        seen: set[str] = set()
        while stack:
            n, kind, depth = stack.pop()
            if n == src:
                continue
            if n in keep:
                cur = found.get((src, n))
                if cur is None or _KIND_RANK[kind] > _KIND_RANK[cur]:
                    found[(src, n)] = kind
                continue
            if n in seen or depth >= 4:
                continue
            seen.add(n)
            stack += [(d, max(kind, k, key=_KIND_RANK.__getitem__), depth + 1) for d, k in out_edges[n]]
    order = {c.id: i for i, c in enumerate(a.components)}
    return sorted(((s, d, k) for (s, d), k in found.items()), key=lambda x: (order[x[0]], order[x[1]]))


# Ana diyagramda gruplar arası bağlar okunabilir bir omurgadan çizilir: soldan sağa
# ana akış + gözetim omurgalarından çapraz bağlar. Veri yolu (hub) indirgenir;
# altyapı grupları alt sırada durur. Tüm bağlar görünüm belgelerinde etiketlidir.
MAIN_FLOW = ("GCS", "COMM", "MC", "SEN", "AIR", "NAV", "EST", "GUID", "CV", "RTA", "CTRL",
             "ALLOC", "FCC", "ACT", "AV")
SUPERVISORY_SOURCES = ("FDIR", "VH", "EN", "MODE", "PRE", "SUP")
INFRASTRUCTURE = ("TIME", "BUS", "CFG", "FDR", "DT")


def _bus_contracted(a: Architecture) -> dict[tuple[str, str], EdgeKind]:
    """Grup düzeyi kenarlar; `X -> BUS_k -> Y` zinciri `X -> Y` olarak indirgenir."""
    agg: dict[tuple[str, str], EdgeKind] = {}

    def put(s: str, d: str, k: EdgeKind) -> None:
        if s != d and (agg.get((s, d)) is None or _KIND_RANK[k] > _KIND_RANK[agg[(s, d)]]):
            agg[(s, d)] = k

    ins: dict[str, list[tuple[str, EdgeKind]]] = {}
    outs: dict[str, list[tuple[str, EdgeKind]]] = {}
    for e in a.edges:
        s, d = top_group(a, e.src), top_group(a, e.dst)
        if s == d:
            continue
        if d == "BUS":
            ins.setdefault(e.dst, []).append((s, e.kind))
        elif s == "BUS":
            outs.setdefault(e.src, []).append((d, e.kind))
        else:
            put(s, d, e.kind)
    for node, sources in ins.items():
        for s, k1 in sources:
            for d, k2 in outs.get(node, []):
                put(s, d, max(k1, k2, key=_KIND_RANK.__getitem__))
    return agg


def spine_edges(a: Architecture) -> list[tuple[str, str, EdgeKind]]:
    main, sup = set(MAIN_FLOW), set(SUPERVISORY_SOURCES)
    out = []
    for (s, d), k in _bus_contracted(a).items():
        if s in main and d in main and k is not EdgeKind.SUPERVISORY:
            out.append((s, d, k))
        elif s in sup and k is EdgeKind.SUPERVISORY and d not in INFRASTRUCTURE:
            out.append((s, d, k))
    order = {g.id: i for i, g in enumerate(a.groups)}
    return sorted(out, key=lambda x: (order[x[0]], order[x[1]]))


def master_diagram(a: Architecture) -> str:
    """Ana sistem diyagramı: `master` bloklar (alt sistem içi bağlarıyla) + omurga."""
    keep = {c.id for c in a.components if c.master}
    lines = ["flowchart LR"] + [f"  {d}" for d in _CLASSDEF]
    for g in a.groups:
        lines += _group_block(a, g.id, keep)
    by_id = a.by_id()
    lines += [f"  {s} {_ARROW[k]} {d}" for s, d, k in projected_edges(a, keep)
              if by_id[s].group == by_id[d].group]
    lines += [f"  {s} {_ARROW[k]} {d}" for s, d, k in spine_edges(a)]
    lines.append("  " + " ~~~ ".join(INFRASTRUCTURE))
    return "\n".join(lines)


# ------------------------------------------------------------------ görünümler
def view_diagram(a: Architecture, groups: tuple[str, ...]) -> str:
    """Seçilen grupların tüm blokları + etiketli bağlantılar + dış komşu kutuları."""
    cont = container_ids(a)
    by_id = a.by_id()
    inside: set[str] = set()
    for gid in groups:
        inside |= set(members(a, gid)) | {gid}
        inside |= {sid for g in a.groups if g.id == gid for sid, _ in g.subgroups}
    lines = ["flowchart LR"] + [f"  {d}" for d in _CLASSDEF]
    for gid in groups:
        lines += _group_block(a, gid)
    ext: dict[str, str] = {}
    edges = [e for e in a.edges if e.src in inside or e.dst in inside]
    for e in edges:
        for n in (e.src, e.dst):
            if n in inside or n in ext:
                continue
            if n in by_id:
                grp = cont[by_id[n].group]
                ext[n] = f'{n}["{_label(by_id[n].name)}<br/><i>{_label(grp)}</i>"]:::ext'
            else:
                ext[n] = f'{n}["{_label(cont[n])}"]:::ext'
    lines += [f"  {v}" for v in ext.values()]
    lines += [f"  {_edge(e, labels=True)}" for e in edges]
    return "\n".join(lines)


def zoom_diagram(a: Architecture, gid: str) -> str:
    return view_diagram(a, (gid,))


# ------------------------------------------------------------------ arıza akışı
def failure_diagram(a: Architecture, chain_id: str) -> str:
    by_id = a.by_id()
    names = lambda ids: "<br/>".join(_label(by_id[i].name) for i in ids)  # noqa: E731
    ch = next(c for c in a.failure_chains if c.id == chain_id)
    return "\n".join([
        "flowchart LR",
        "  classDef fault fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a;",
        "  classDef stage fill:#f6f8fa,stroke:#57606a,color:#24292f;",
        "  classDef record fill:#ddf4ff,stroke:#0969da,color:#0a3069;",
        f'  F["FAULT<br/>{_label(ch.fault)}"]:::fault',
        f'  D["DETECTION<br/>{names(ch.detection)}"]:::stage',
        f'  I["ISOLATION<br/>{names(ch.isolation)}"]:::stage',
        f'  G["DEGRADATION<br/>{names(ch.degradation)}"]:::stage',
        f'  C["CONTINGENCY<br/>{names(ch.contingency)}"]:::stage',
        f'  E["EVENT / RECORD<br/>{"<br/>".join(ch.events)}"]:::record',
        "  F --> D --> I --> G --> C --> E"])


def failure_diagrams(a: Architecture) -> str:
    parts = []
    for ch in a.failure_chains:
        parts += [f"**{ch.title}** — senaryo `{ch.scenario}`: {ch.outcome}", "",
                  f"```mermaid\n{failure_diagram(a, ch.id)}\n```", ""]
    return "\n".join(parts).rstrip()


def failure_table(a: Architecture) -> str:
    by_id = a.by_id()
    nm = lambda ids: ", ".join(by_id[i].name for i in ids)  # noqa: E731
    rows = ["| Arıza | Fault | Detection | Isolation | Degradation | Contingency | Event / Record | "
            "Senaryo (testli) | Sonuç |", "|---|---|---|---|---|---|---|---|---|"]
    for ch in a.failure_chains:
        rows.append(f"| **{ch.title}** | {_cell(ch.fault)} | {nm(ch.detection)} | {nm(ch.isolation)} | "
                    f"{nm(ch.degradation)} | {nm(ch.contingency)} | "
                    f"{', '.join(f'`{e}`' for e in ch.events)} | `{ch.scenario}` | {_cell(ch.outcome)} |")
    return "\n".join(rows)


# ------------------------------------------------------------------ tablolar
def status_summary(a: Architecture) -> str:
    cont = container_ids(a)
    head = " | ".join(s.value for s in _STATUS_ORDER)
    rows = [f"| Alt sistem | Blok | {head} | Ana diyagramda |",
            "|---|---:|" + "---:|" * len(_STATUS_ORDER) + "---:|"]
    total: Counter = Counter()
    n_master = 0
    for g in a.groups:
        cs = [c for c in a.components if c.group == g.id]
        cnt = Counter(c.status for c in cs)
        total.update(cnt)
        m = sum(c.master for c in cs)
        n_master += m
        rows.append(f"| {cont[g.id]} | {len(cs)} | " + " | ".join(str(cnt[s]) for s in _STATUS_ORDER)
                    + f" | {m} |")
    rows.append(f"| **Toplam ({len(a.groups)} alt sistem)** | **{sum(total.values())}** | "
                + " | ".join(f"**{total[s]}**" for s in _STATUS_ORDER) + f" | **{n_master}** |")
    return "\n".join(rows)


def _cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ")


def component_matrix(a: Architecture, groups: tuple[str, ...] | None = None) -> str:
    cont = container_ids(a)
    out = []
    for g in a.groups:
        if groups is not None and g.id not in groups:
            continue
        out += [f"#### {cont[g.id]}", "",
                "| Component | Responsibility | Inputs | Outputs | Health State | Failure Behaviour | "
                "Code Location | Implementation Status |",
                "|---|---|---|---|---|---|---|---|"]
        for c in (x for x in a.components if x.group == g.id):
            code = "<br/>".join(f"`{r}`" for r in c.code) or "—"
            status = c.status.value + (f" — {_cell(c.note)}" if c.note else "")
            name = f"**{_cell(c.name)}** `{c.id}`" + (" *(öneri)*" if c.proposal_only else "") \
                + (" *(geçit)*" if c.id in a.gates else "")
            red = f" Yedeklilik: {_cell(c.redundancy)}." if c.redundancy else ""
            out.append(f"| {name} | {_cell(c.responsibility)} | {_cell(c.inputs)} | "
                       f"{_cell(c.outputs)} | {_cell(c.health)} | {_cell(c.failure or '—')}{red} | "
                       f"{code} | {status} |")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def audit_table(a: Architecture) -> str:
    rows = ["| Denetim | Sonuç | Kanıt |", "|---|---|---|"]
    for r in audit.run(a):
        rows.append(f"| {r.check} | {'GEÇTİ' if r.passed else '**KALDI**'} | {_cell(r.detail)} |")
    return "\n".join(rows)


def spof_table(a: Architecture) -> str:
    by_id, mit = a.by_id(), dict(a.spof_mitigation)
    rows = ["| Blok | Alt sistem | Neden aday | Azaltım / durum |", "|---|---|---|---|"]
    cont = container_ids(a)
    for n in audit.spof_candidates(a):
        c = by_id[n]
        why = "öneri katmanı (yetkisiz)" if c.proposal_only else "komut yolunda, yedek örnek yok"
        rows.append(f"| {c.name} `{n}` | {cont[c.group]} | {why} | {_cell(mit.get(n, '**YOK**'))} |")
    return "\n".join(rows)


def failsafe_table() -> str:
    rows = ["| Fail-safe kuralı | Zorlayan test(ler) |", "|---|---|"]
    for rule, tests in audit.FAILSAFE_RULES:
        rows.append(f"| {rule} | " + "<br/>".join(f"`{t}`" for t in tests) + " |")
    return "\n".join(rows)


def invariants_table() -> str:
    rows = ["| Güvenlik değişmezi | Zorlayan test(ler) |", "|---|---|"]
    for rule, tests in audit.SAFETY_INVARIANTS:
        rows.append(f"| {rule} | " + "<br/>".join(f"`{t}`" for t in tests) + " |")
    return "\n".join(rows)


def blocks(a: Architecture) -> dict[str, str]:
    """Belgelere yerleştirilen üretilmiş bloklar: anahtar -> içerik."""
    mm = lambda body: f"```mermaid\n{body}\n```"  # noqa: E731
    b = {"master": mm(master_diagram(a)), "status": status_summary(a),
         "matrix": component_matrix(a), "failure-chains": failure_diagrams(a),
         "failure-table": failure_table(a), "audit": audit_table(a), "spof": spof_table(a),
         "failsafe": failsafe_table(), "invariants": invariants_table()}
    for v in a.views:
        b[f"view-{v.id}"] = mm(view_diagram(a, v.groups))
        b[f"matrix-{v.id}"] = component_matrix(a, v.groups)
    return b


def view_by_id(a: Architecture, vid: str) -> View:
    return next(v for v in a.views if v.id == vid)
