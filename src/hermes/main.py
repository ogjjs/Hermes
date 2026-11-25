"""Inicializador único do Hermes (hoje, só a linha de comando)."""

from __future__ import annotations

import sys

from hermes.interface.cli import main as cli


def main() -> int:
    return cli(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
