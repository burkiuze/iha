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

_RX = re.compile(r"(?P<begin><!-- BEGIN GENERATED: (?P<key>[\w-]+) -->)(?P<body>.*?)"
                 r"(?P<end><!-- END GENERATED: (?P=key) -->)", re.S)


def render_document(text: str) -> str:
    gen = blocks(ARCHITECTURE)

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
    a = p.parse_args(argv)
    path = Path(a.update or a.check)
    text = path.read_text(encoding="utf-8")
    new = render_document(text)
    if a.update:
        path.write_text(new, encoding="utf-8")
        print(f"güncellendi: {path} ({len(generated_keys(text))} blok)")
        return 0
    if new != text:
        print(f"{path} kayıtla senkron değil; --update çalıştırın", file=sys.stderr)
        return 1
    print("senkron")
    return 0


if __name__ == "__main__":
    sys.exit(main())
