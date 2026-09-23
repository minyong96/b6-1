"""로그는 stderr, 결과물은 stdout으로 분리한다 (결과만 파이프/리다이렉트 가능)."""

from __future__ import annotations

import sys


def info(msg: str) -> None:
    print(f"[INFO] {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    print(f"[WARN] {msg}", file=sys.stderr)


def error(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)


def done(msg: str) -> None:
    print(f"[DONE] {msg}", file=sys.stderr)
