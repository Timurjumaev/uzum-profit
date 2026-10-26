"""B4.2a Uzum bonuslari (ADR-031): ``/fee-waivers`` CRUD (haqiqiy PostgreSQL) — ruxsatlar, tekshiruvlar, audit,
takliflarni tasdiqlash/rad etish, sotuv qatoridagi "bonus davri" belgisi va tashkilotlarni ajratish.

Dunyo (``world``) — ``test_reports`` dagi bilan bir xil, lekin shu modul uchun alohida (o'zgartirishlar u yerga
ta'sir qilmaydi). Bonus haqiqiy foydani o'zgartirmasligi — ``test_reports.test_waivers_do_not_change_actual_profit``.
"""

from __future__ import annotations

import uuid
from typing import Any

import test_reports
from test_reports import AUG, World, d, suggestion
from upapi.auth.deps import COOKIE

# Fixture'lar shu modulda qayta e'lon qilinadi — modul doirasida alohida nusxa.
db = test_reports.db
world = test_reports.world
PATH = "fee-waivers"


def send(w: World, method: str, path: str = PATH, role: str = "owner", **body: Any) -> Any:
    w.api.client.cookies.set(COOKIE, w.sessions[role])
    url = f"/api/v1/orgs/{w.org_id}/{path}"
    if method == "delete":
        return w.api.client.delete(url)
    return getattr(w.api.client, method)(url, json=body)


def waiver(**extra: Any) -> dict[str, Any]:
    return {
        "start_on": "2026-10-10",
        "end_on": "2026-10-31",
        "kinds": ["storage", "sale_logistics"],
        "reason": "  Uzum nosozligi uchun kompensatsiya ",
        **extra,
    }


def audit(w: World, entity_id: str) -> list[tuple[str, Any, Any]]:
    rows = w.api.admin(
        "SELECT action, before, after FROM audit_log WHERE entity = 'fee_waiver' AND entity_id = %s "
        "ORDER BY created_at, action",
        [entity_id],
    )
    return [tuple(r) for r in rows]


def test_list_and_kinds(world: World) -> None:
    body = world.get(PATH)
    assert body["kinds"][0] == "sale_logistics" and "storage" in body["kinds"]
    assert "compensation" not in body["kinds"]
    [item] = body["items"]  # fixture'dagi A do'koni, 12-avgust
    assert item["id"] == str(world.ids["waiver"]) and item["shop_id"] == str(world.a.shop_id)
    assert item["kinds"] == ["sale_logistics", "storage"] and not item["dismissed"]
    assert world.get(PATH, role="accountant")["items"] == body["items"]  # o'qish — view_finance
    assert world.call(PATH, role="warehouse").status_code == 403


def test_create_update_delete_with_audit(world: World) -> None:
    r = send(world, "post", **waiver())
    assert r.status_code == 201, r.text
    created = r.json()
    wid = created["id"]
    # Turlar ruxsat etilgan tartibda, sabab tozalangan; do'konsiz — hamma do'kon.
    assert created["kinds"] == ["sale_logistics", "storage"]
    assert created["reason"] == "Uzum nosozligi uchun kompensatsiya"
    assert created["shop_id"] is None and created["source"] == "manual"

    r = send(world, "patch", f"{PATH}/{wid}", end_on="2026-10-20", kinds=["storage"])
    assert r.status_code == 200, r.text
    assert r.json()["end_on"] == "2026-10-20" and r.json()["kinds"] == ["storage"]
    assert send(world, "patch", f"{PATH}/{wid}", reason=None).json()["reason"] == created["reason"]

    assert send(world, "delete", f"{PATH}/{wid}").status_code == 204
    assert send(world, "delete", f"{PATH}/{wid}").status_code == 404
    actions = audit(world, wid)
    assert [a[0] for a in actions] == [
        "fee_waiver.create",
        "fee_waiver.update",
        "fee_waiver.delete",
    ]
    assert actions[0][2]["start_on"] == "2026-10-10" and actions[0][2]["shop_id"] is None
    assert actions[1][1] == {"end_on": "2026-10-31", "kinds": ["sale_logistics", "storage"]}
    assert actions[2][1]["reason"] == "Uzum nosozligi uchun kompensatsiya"


def test_validation(world: World) -> None:
    def code(**extra: Any) -> tuple[int, str]:
        r = send(world, "post", **waiver(**extra))
        return r.status_code, r.json().get("code", "")

    assert code(end_on="2026-10-01") == (422, "bad_period")
    assert code(start_on="2025-01-01") == (422, "bad_period")  # 366 kundan uzun
    assert code(kinds=[]) == (422, "bad_kinds")
    assert code(kinds=["compensation"]) == (422, "bad_kinds")
    assert code(shop_id=str(uuid.uuid4())) == (404, "shop_not_found")
    assert code(reason="x" * 301)[0] == 422
    assert code(source="robot")[0] == 422
    other = send(world, "post", **waiver()).json()["id"]
    r = send(world, "patch", f"{PATH}/{other}", start_on="2026-11-01")
    assert (r.status_code, r.json()["code"]) == (422, "bad_period")
    r = send(world, "patch", f"{PATH}/{other}", kinds=None)
    assert r.status_code == 422
    r = send(world, "patch", f"{PATH}/{other}", shop_id=str(uuid.uuid4()))
    assert (r.status_code, r.json()["code"]) == (404, "shop_not_found")
    assert send(world, "patch", f"{PATH}/{uuid.uuid4()}", reason="x").status_code == 404
    assert send(world, "delete", f"{PATH}/{other}").status_code == 204


def test_permissions(world: World) -> None:
    assert send(world, "post", role="accountant", **waiver()).status_code == 403
    assert send(world, "post", role="warehouse", **waiver()).status_code == 403
    r = send(world, "post", role="manager", **waiver(shop_id=str(world.b.shop_id)))
    assert r.status_code == 201
    wid = r.json()["id"]
    assert send(world, "delete", f"{PATH}/{wid}", role="accountant").status_code == 403
    assert send(world, "delete", f"{PATH}/{wid}", role="manager").status_code == 204


def test_confirm_and_dismiss_suggestions(world: World) -> None:
    before = world.get("pnl", **AUG)["waiver_suggestions"]
    assert suggestion(world.b, d(8, 10)) in before and suggestion(world.a, d(8, 10)) in before

    # Tasdiqlash: taklifdan (source=detected) davr — endi faol, taklif yo'qoladi, sotuv belgilanadi.
    on = "2026-08-10"
    r = send(
        world,
        "post",
        **waiver(
            shop_id=str(world.b.shop_id),
            start_on=on,
            end_on=on,
            kinds=["sale_logistics"],
            source="detected",
        ),
    )
    confirmed = r.json()["id"]
    # Rad etish: A do'koni taklifi — qayta taklif qilinmaydi, hech narsaga ta'sir qilmaydi.
    r = send(
        world,
        "post",
        **waiver(
            shop_id=str(world.a.shop_id),
            start_on=on,
            end_on=on,
            kinds=["sale_logistics"],
            reason="",
            dismissed=True,
        ),
    )
    dismissed = r.json()
    assert dismissed["dismissed"] and dismissed["source"] == "manual"
    assert [a[0] for a in audit(world, dismissed["id"])] == ["fee_waiver.dismiss"]

    body = world.get("pnl", **AUG)
    assert body["waiver_suggestions"] == []
    assert confirmed in {x["id"] for x in body["waivers"]}
    assert dismissed["id"] not in {x["id"] for x in body["waivers"]}  # rad etilgani — bannerda yo'q

    sales = world.get("sales", group="completed", **AUG)["items"]
    marks = {(s["shop_id"], s["day"]): s["waiver_id"] for s in sales}
    assert marks[(str(world.b.shop_id), "2026-08-10")] == confirmed
    assert marks[(str(world.b.shop_id), "2026-08-11")] is None
    assert marks[(str(world.a.shop_id), "2026-08-10")] is None  # rad etilgan — belgilamaydi
    assert marks[(str(world.a.shop_id), "2026-08-12")] == str(world.ids["waiver"])


def test_other_org_is_invisible(world: World) -> None:
    wid = send(world, "post", **waiver()).json()["id"]
    world.api.client.cookies.set(COOKIE, world.sessions["owner"])
    other = f"/api/v1/orgs/{world.other}/{PATH}"
    assert world.api.client.get(other).status_code in (403, 404)
    # Boshqa tashkilot yozuvi bu tashkilot yo'li orqali ham ko'rinmaydi va o'zgarmaydi (RLS).
    rows = world.api.admin("SELECT id FROM fee_waivers WHERE org_id = %s", [world.other])
    assert rows == []
    foreign = world.api.admin(
        "INSERT INTO fee_waivers (org_id, start_on, end_on, kinds) VALUES (%s, '2026-10-01', '2026-10-02', "
        "ARRAY['storage']) RETURNING id",
        [world.other],
    )[0][0]
    assert send(world, "patch", f"{PATH}/{foreign}", reason="x").status_code == 404
    assert send(world, "delete", f"{PATH}/{foreign}").status_code == 404
    assert str(foreign) not in {x["id"] for x in world.get(PATH)["items"]}
    assert send(world, "delete", f"{PATH}/{wid}").status_code == 204
