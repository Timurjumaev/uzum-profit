"""Yozib olingan Uzum javoblari (kassetalar, ``fixtures/uzum/*.json``) va ularni qaytaruvchi transport.

Kasseta formati — ``scripts/record_uzum.py`` chiqishi: ``interactions`` (nom, so'rov yo'li va parametrlari, javob
holati, sarlavhalari va tanasi). Matnli tana ``{"__text__": "..."}`` ko'rinishida (WAF HTML va h.k.).

- ``synthetic.json`` — legacy maydon nomlari asosida qo'lda yozilgan (haqiqiy javob emas);
- ``recorded*.json`` — Temurning Mac'ida haqiqiy kalit bilan yozilgan va anonimlashtirilgan.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).parent / "fixtures" / "uzum"


@dataclass
class Interaction:
    name: str
    path: str
    params: dict[str, Any]
    status: int
    headers: dict[str, str]
    body: Any

    def response(self) -> httpx.Response:
        if isinstance(self.body, dict) and set(self.body) == {"__text__"}:
            return httpx.Response(self.status, headers=self.headers, content=self.body["__text__"])
        return httpx.Response(self.status, headers=self.headers, json=self.body)


@dataclass
class Cassette:
    file: str
    source: str
    interactions: list[Interaction]
    probes: list[dict[str, Any]] = field(default_factory=list)

    def get(self, name: str) -> Interaction | None:
        return next((i for i in self.interactions if i.name == name), None)


def load(path: Path) -> Cassette:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Cassette(
        file=path.name,
        source=data["source"],
        interactions=[
            Interaction(
                name=i["name"],
                path=i["request"]["path"],
                params=i["request"]["params"],
                status=i["response"]["status"],
                headers=i["response"]["headers"],
                body=i["response"]["body"],
            )
            for i in data["interactions"]
        ],
        probes=data.get("probes", []),
    )


def all_cassettes() -> list[Cassette]:
    return [load(p) for p in sorted(FIXTURES.glob("*.json"))]


@dataclass
class Replay:
    """Bitta javobni qaytaradi: so'rov yo'li mos bo'lsa (sahifa 0 dan boshqasi — bo'sh ro'yxat emas, 404)."""

    interaction: Interaction
    seen: list[httpx.Request] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if not request.url.path.endswith(self.interaction.path):
            return httpx.Response(404, json={"error": "cassette: boshqa yo'l"})
        if request.url.params.get("page", "0") != "0":
            return httpx.Response(404, json={"error": "cassette: faqat 0-sahifa yozilgan"})
        return self.interaction.response()

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)
