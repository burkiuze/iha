"""Belgedeki üretilmiş blokları kayıttan günceller ya da senkronluğu denetler.

Bloklar şu işaretler arasındadır:
    <!-- BEGIN GENERATED: <anahtar> -->
    ...
    <!-- END GENERATED: <anahtar> -->
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .registry import ARCHITECTURE
from .render import blocks

ROOT = Path(__file__).resolve().parents[2]


def architecture_documents() -> list[Path]:
    """Üretilmiş blok içeren tüm mimari belgeleri (docs/15 + docs/mimari/*.md)."""
    return [ROOT / "docs" / "15-sistem-mimarisi.md"] + sorted((ROOT / "docs" / "mimari").glob("*.md"))

_RX = re.compile(r"(?P<begin><!-- BEGIN GENERATED: (?P<key>[\w-]+) -->)(?P<body>.*?)"
                 r"(?P<end><!-- END GENERATED: (?P=key) -->)", re.S)


def render_document(text: str, gen: dict[str, str] | None = None) -> str:
    gen = blocks(ARCHITECTURE) if gen is None else gen

    def sub(m: re.Match) -> str:
        key = m.group("key")
        if key not in gen:
            raise KeyError(f"bilinmeyen üretilmiş blok: {key}")
        return m.group("begin") + "\n" + gen[key].rstrip("\n") + "\n" + m.group("end")

    return _RX.sub(sub, text)


def generated_keys(text: str) -> list[str]:
    return [m.group("key") for m in _RX.finditer(text)]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m simurg.architecture")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--update", metavar="MD")
    g.add_argument("--check", metavar="MD")
    g.add_argument("--update-all", action="store_true", help="docs/15 + docs/mimari/*.md")
    g.add_argument("--check-all", action="store_true", help="docs/15 + docs/mimari/*.md")
    a = p.parse_args(argv)
    paths = architecture_documents() if (a.update_all or a.check_all) else [Path(a.update or a.check)]
    update = bool(a.update or a.update_all)
    gen = blocks(ARCHITECTURE)
    stale = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        new = render_document(text, gen)
        if update:
            path.write_text(new, encoding="utf-8")
            print(f"güncellendi: {path} ({len(generated_keys(text))} blok)")
        elif new != text:
            stale.append(path)
    if stale:
        for path in stale:
            print(f"{path} kayıtla senkron değil; --update-all çalıştırın", file=sys.stderr)
        return 1
    if not update:
        print("senkron")
    return 0


if __name__ == "__main__":
    sys.exit(main())
