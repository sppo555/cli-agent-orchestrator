"""Render captured Grok ANSI streams through pyte for Phase 0 evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

import pyte


def render(source: Path, target: Path, columns: int = 120, rows: int = 40) -> None:
    screen = pyte.Screen(columns, rows)
    stream = pyte.Stream(screen)
    stream.feed(source.read_bytes().decode("utf-8", errors="replace"))
    target.write_text("\n".join(screen.display) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--columns", type=int, default=120)
    parser.add_argument("--rows", type=int, default=40)
    args = parser.parse_args()
    render(args.source, args.target, args.columns, args.rows)


if __name__ == "__main__":
    main()
