"""Kayıttan Mermaid diyagramları ve Markdown tabloları üretir (deterministik)."""

from __future__ import annotations

from collections import Counter

from .model import Architecture, Component, Edge, EdgeKind, Status

_ARROW = {EdgeKind.DATA: "-->", EdgeKind.COMMAND: "==>", EdgeKind.SUPERVISORY: "-.->"}
_CLASSDEF = (
    "classDef implemented fill:#d7f5dd,stroke:#1a7f37,color:#0b3d1a;",
    "classDef partial fill:#fff4c2,stroke:#9a6700,color:#3d2e00;",
    "classDef planned fill:#eef0f3,stroke:#8c959f,color:#57606a,stroke-dasharray: 4 3;",
    "classDef gate fill:#ffd8d8,stroke:#cf222e,color:#5c0a0a,stroke-width:3px;",
    "classDef ext fill:#ffffff,stroke:#8c959f,color:#57606a;",
)


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
    return [c.id for c in a.components if c.group == container or c.sub == container]


def _edge(e: Edge, labels: bool) -> str:
    arrow = _ARROW[e.kind]
    if labels and e.label:
        return f'{e.src} {arrow}|"{_label(e.label)}"| {e.dst}'
    return f"{e.src} {arrow} {e.dst}"


def _group_block(a: Architecture, gid: str, indent: str = "  ") -> list[str]:
    g = next(x for x in a.groups if x.id == gid)
    lines = [f'{indent}subgraph {g.id}["{_label(g.title)}"]', f"{indent}  direction TB"]
    for sid, title in g.subgroups:
        nodes = [c for c in a.components if c.group == gid and c.sub == sid]
        if not nodes:
            continue
        lines.append(f'{indent}  subgraph {sid}["{_label(title)}"]')
        lines += [f"{indent}    {_node(c, a.gates)}" for c in nodes]
        lines.append(f"{indent}  end")
    lines += [f"{indent}  {_node(c, a.gates)}" for c in a.components if c.group == gid and not c.sub]
    lines.append(f"{indent}end")
    return lines


def top_group(a: Architecture, node: str) -> str:
    """Düğüm, alt grup ya da grup kimliği -> üst grup kimliği."""
    by_id = a.by_id()
    if node in by_id:
        return by_id[node].group
    for g in a.groups:
        if node == g.id or node in {sid for sid, _ in g.subgroups}:
            return g.id
    raise KeyError(node)


_KIND_RANK = {EdgeKind.DATA: 0, EdgeKind.SUPERVISORY: 1, EdgeKind.COMMAND: 2}


def group_edges(a: Architecture) -> list[tuple[str, str, EdgeKind]]:
    """Gruplar arası kenarları toplar; tür önceliği: komut > gözetim > veri."""
    agg: dict[tuple[str, str], EdgeKind] = {}
    for e in a.edges:
        s, d = top_group(a, e.src), top_group(a, e.dst)
        if s == d:
            continue
        cur = agg.get((s, d))
        if cur is None or _KIND_RANK[e.kind] > _KIND_RANK[cur]:
            agg[(s, d)] = e.kind
    order = {g.id: i for i, g in enumerate(a.groups)}
    return sorted(((s, d, k) for (s, d), k in agg.items()), key=lambda x: (order[x[0]], order[x[1]]))


# Tam diyagramda gruplar arası bağlantılar yalnızca okunabilir bir omurgadan
# çizilir: ana akış (soldan sağa) + gözetim kaynaklarından çapraz bağlantılar.
# Altyapı grupları (veri yolu, zaman, yapılandırma, kayıt, ikiz) kendi
# yakınlaştırmalarında (§5) tüm kenarlarıyla gösterilir.
MAIN_FLOW = ("GCS", "COMM", "MC", "SEN", "NAV", "GNC", "RTA",
             "LANEA", "LANEB", "LANEC", "LANEM", "ALLOC", "ACT")
SUPERVISORY_SOURCES = ("RTA", "FDIR", "EN", "MODE", "PRE", "SUP")
INFRASTRUCTURE = ("BUS", "TIME", "CFG", "FDR", "DT")


def _bus_contracted(a: Architecture) -> dict[tuple[str, str], EdgeKind]:
    """Veri yolu üzerinden geçen akışı doğrudan grup bağına indirger.

    ``X -> BUS_k -> Y`` zinciri ``X -> Y`` olarak, iki kenardan baskın türle
    (komut > gözetim > veri) temsil edilir; veri yolu bir merkez (hub) olduğundan
    tam diyagramda doğrudan çizilmesi okunabilirliği bozar.
    """
    agg: dict[tuple[str, str], EdgeKind] = {}

    def put(s: str, d: str, k: EdgeKind) -> None:
        if s == d:
            return
        cur = agg.get((s, d))
        if cur is None or _KIND_RANK[k] > _KIND_RANK[cur]:
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
    """Tam diyagramda çizilen grup düzeyi kenarlar (veri yolu indirgenmiş)."""
    main, sup = set(MAIN_FLOW), set(SUPERVISORY_SOURCES)
    out = []
    for (s, d), k in _bus_contracted(a).items():
        if s in main and d in main and k is not EdgeKind.SUPERVISORY:
            out.append((s, d, k))
        elif s in sup and k is EdgeKind.SUPERVISORY and d not in INFRASTRUCTURE:
            out.append((s, d, k))
    order = {g.id: i for i, g in enumerate(a.groups)}
    return sorted(out, key=lambda x: (order[x[0]], order[x[1]]))


def full_diagram(a: Architecture) -> str:
    """Tüm bileşenler + grup içi kenarlar + gruplar arası omurga (bkz. ``spine_edges``)."""
    lines = ["flowchart LR"] + [f"  {d}" for d in _CLASSDEF]
    for g in a.groups:
        lines += _group_block(a, g.id)
    for e in a.edges:
        if top_group(a, e.src) == top_group(a, e.dst):
            lines.append(f"  {_edge(e, labels=False)}")
    lines += [f"  {s} {_ARROW[k]} {d}" for s, d, k in spine_edges(a)]
    # Altyapı gruplarını tek sırada tutan görünmez bağlar (yerleşim ipucu)
    lines.append("  " + " ~~~ ".join(INFRASTRUCTURE))
    return "\n".join(lines)


def zoom_diagram(a: Architecture, gid: str) -> str:
    """Bir grup + doğrudan komşuları (dış düğümler sade kutu olarak)."""
    cont = container_ids(a)
    by_id = a.by_id()
    inside = set(members(a, gid)) | {sid for g in a.groups if g.id == gid for sid, _ in g.subgroups}
    inside.add(gid)
    lines = ["flowchart LR"] + [f"  {d}" for d in _CLASSDEF]
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


def status_summary(a: Architecture) -> str:
    cont = container_ids(a)
    rows = ["| Grup | Bileşen | IMPLEMENTED | PARTIAL | PLANNED |", "|---|---:|---:|---:|---:|"]
    total = Counter()
    for g in a.groups:
        cnt = Counter(c.status for c in a.components if c.group == g.id)
        n = sum(cnt.values())
        total.update(cnt)
        rows.append(f"| {cont[g.id]} | {n} | {cnt[Status.IMPLEMENTED]} | {cnt[Status.PARTIAL]} | "
                    f"{cnt[Status.PLANNED]} |")
    rows.append(f"| **Toplam** | **{sum(total.values())}** | **{total[Status.IMPLEMENTED]}** | "
                f"**{total[Status.PARTIAL]}** | **{total[Status.PLANNED]}** |")
    return "\n".join(rows)


def _cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ")


def component_matrix(a: Architecture) -> str:
    cont = container_ids(a)
    out = []
    for g in a.groups:
        out += [f"#### {cont[g.id]}", "",
                "| Component | Responsibility | Inputs | Outputs | Health/Fault State | Code Location | Status |",
                "|---|---|---|---|---|---|---|"]
        for c in (x for x in a.components if x.group == g.id):
            code = "<br/>".join(f"`{r}`" for r in c.code) or "—"
            status = c.status.value + (f" — {_cell(c.note)}" if c.note else "")
            name = f"**{_cell(c.name)}** `{c.id}`" + (" *(öneri)*" if c.proposal_only else "")
            out.append(f"| {name} | {_cell(c.responsibility)} | {_cell(c.inputs)} | "
                       f"{_cell(c.outputs)} | {_cell(c.health)} | {code} | {status} |")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def blocks(a: Architecture) -> dict[str, str]:
    """Belgeye yerleştirilen üretilmiş bloklar: anahtar -> içerik."""
    b = {"full": f"```mermaid\n{full_diagram(a)}\n```",
         "status": status_summary(a), "matrix": component_matrix(a)}
    for g in a.groups:
        b[f"zoom-{g.id}"] = f"```mermaid\n{zoom_diagram(a, g.id)}\n```"
    return b
