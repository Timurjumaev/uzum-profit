"""OpenAPI sxemasi fayli (03 §8, §13): ``apps/api/openapi.json`` — frontend tiplari manbasi
(``apps/web/src/lib/api/schema.d.ts``, ``pnpm --filter web api:types``).

``uv run python -m upapi.openapi`` — faylni yangilaydi; ``--check`` — kod bilan farq bo'lsa xato (CI va
``tests/test_reports.py``). API o'zgarsa ikkala buyruq ham ishga tushiriladi, aks holda CI qizaradi.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from upapi.main import create_app
from upapi.settings import Environment, Settings

PATH = Path(__file__).resolve().parents[2] / "openapi.json"


def render() -> str:
    app = create_app(Settings(env=Environment.TEST))
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        if not PATH.exists() or PATH.read_text() != text:
            print(f"{PATH} eskirgan: uv run python -m upapi.openapi", file=sys.stderr)
            return 1
        return 0
    PATH.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
