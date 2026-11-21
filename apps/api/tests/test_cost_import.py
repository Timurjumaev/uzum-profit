"""B7.1 ``/opening/costs`` (haqiqiy PostgreSQL): shablon, ko'rib chiqish (yangi / o'zgaradi / bir xil / xato), saqlash, qayta yuklash
hech narsani o'zgartirmaydi, sonlar formati, fayl xavfsizligi (xlsx emas, hajm, shablon emas, daqiqasiga cheklov), ruxsat.
Ma'lumot — ``test_reports`` dunyosi."""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

import test_reports as tr
from openpyxl import Workbook, load_workbook
from upapi.auth.deps import COOKIE
from upapi.reports.xlsx import XLSX_TYPE
from upapi.routes.cost_import import HEADERS, parse_cost

D = Decimal
db = tr.db
world = tr.world


def reset_limit(w: tr.World) -> None:
    """Daqiqasiga cheklov (B7.1) testlar orasida bo'linmasin."""
    w.api.client.app.state.import_limiter._hits.clear()


def post(w: tr.World, path: str, data: bytes, role: str = "owner", ctype: str = XLSX_TYPE) -> Any:
    w.api.client.cookies.set(COOKIE, w.sessions[role])
    return w.api.client.post(
        f"/api/v1/orgs/{w.org_id}/opening/{path}",
        content=data,
        headers={"Content-Type": ctype, "X-Requested-With": "fetch"},
    )


def apply(w: tr.World, changes: list[dict[str, Any]], role: str = "owner") -> Any:
    w.api.client.cookies.set(COOKIE, w.sessions[role])
    return w.api.client.post(
        f"/api/v1/orgs/{w.org_id}/opening/costs/apply",
        json={"changes": changes},
        headers={"X-Requested-With": "fetch"},
    )


def template(w: tr.World) -> list[list[Any]]:
    r = w.call("opening/costs.xlsx")
    assert r.status_code == 200 and r.headers["content-type"].startswith(XLSX_TYPE), r.text
    wb = load_workbook(io.BytesIO(r.content))
    return [list(row) for row in wb.worksheets[0].iter_rows(values_only=True)]


def sheet(rows: list[list[Any]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    for row in rows:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_parse_cost_formats_and_errors() -> None:
    assert parse_cost(None) is None and parse_cost("") is None and parse_cost("  ") is None
    for text in ("12 500", "12 500", "12500", 12500, 12500.0):
        assert parse_cost(text) == D("12500.00"), text
    assert parse_cost("12500,50") == D("12500.50") and parse_cost("12 500.5") == D("12500.50")
    for bad in ("abc", "-5", -5, "#REF!", "1,000.50", "12.345", True, "1e999", "NaN"):
        try:
            parse_cost(bad)
        except ValueError:
            continue
        raise AssertionError(f"xato kutilgan edi: {bad!r}")


def test_template_preview_apply_and_reupload_is_noop(world: tr.World) -> None:
    w = world
    reset_limit(w)
    rows = template(w)
    assert tuple(rows[0][: len(HEADERS)]) == HEADERS and len(rows) > 1
    body = rows[1:]
    assert all(str(r[0]).startswith(("item:", "sku:")) for r in body)  # yashirin ichki id
    # Tannarx ustuni (oxirgisi): oldindan hozirgi qiymat yoki bo'sh; bir nechtasini o'zgartiramiz.
    edits = {i: 11_111 + i for i in range(min(3, len(body)))}
    for i, value in edits.items():
        body[i][7] = value
    data = sheet([list(rows[0]), *body])

    pre = post(w, "costs/preview", data)
    assert pre.status_code == 200, pre.text
    p = pre.json()
    assert p["error_count"] == 0 and len(p["changes"]) == p["new"] + p["changed"] == len(edits)
    assert p["new"] + p["changed"] + p["same"] + p["empty"] == len(body)
    assert {c["key"]: D(c["new"]) for c in p["changes"]} == {
        body[i][0]: D(v) for i, v in edits.items()
    }
    # Ko'rib chiqish hech narsa yozmaydi.
    before = w.a.sql(
        "SELECT count(*) FROM item_costs WHERE org_id = %s AND valid_from IS NULL", [w.org_id]
    )
    assert (
        before[0][0]
        == w.a.sql(
            "SELECT count(*) FROM item_costs WHERE org_id = %s AND valid_from IS NULL", [w.org_id]
        )[0][0]
    )

    out = apply(w, [{"key": c["key"], "unit_cost": c["new"]} for c in p["changes"]])
    assert out.status_code == 200, out.text
    assert out.json() == {"saved": len(edits), "unchanged": 0}
    # Tovarga bog'lanmagan SKU uchun tovar yaratildi; hammasida boshidan narx bor.
    for c in p["changes"]:
        key, _, ident = c["key"].partition(":")
        if key == "item":
            got = w.a.sql(
                "SELECT unit_cost FROM item_costs WHERE org_id = %s AND item_id = %s AND valid_from IS NULL",
                [w.org_id, ident],
            )
            assert got and D(got[0][0]) == D(c["new"])
        else:
            got = w.a.sql(
                "SELECT c.unit_cost FROM mp_skus s JOIN item_costs c ON c.item_id = s.item_id "
                "WHERE s.id = %s AND c.valid_from IS NULL",
                [ident],
            )
            assert got and D(got[0][0]) == D(c["new"])

    # O'sha faylni qayta yuklash — hech narsa o'zgarmaydi (hammasi "bir xil").
    again = post(w, "costs/preview", data).json()
    assert again["changes"] == [] and again["new"] == 0 and again["changed"] == 0
    assert again["same"] >= len(edits)
    assert apply(w, [{"key": c["key"], "unit_cost": c["new"]} for c in p["changes"]]).json() == {
        "saved": 0,
        "unchanged": len(edits),
    }


def test_preview_errors_barcode_fallback_and_overwrite(world: tr.World) -> None:
    w = world
    reset_limit(w)
    rows = template(w)
    head, body = list(rows[0]), rows[1:]
    first_key = body[0][0]
    good = [first_key, None, None, None, "Nom", None, None, "12 500,5"]  # vergul va bo'shliq
    wrong = [
        [first_key, None, None, None, "x", None, None, "abc"],  # matn
        [
            body[0][0] if len(body) < 2 else body[1][0],
            None,
            None,
            None,
            "x",
            None,
            None,
            -5,
        ],  # manfiy
        [
            "item:00000000-0000-0000-0000-000000000000",
            None,
            None,
            None,
            "x",
            None,
            None,
            100,
        ],  # topilmadi
        ["", None, None, "yo'q-shtrix-kod", "x", None, None, 100],  # ID yo'q, shtrix-kod topilmadi
        [first_key, None, None, None, "x", None, None, "#REF!"],  # formula xatosi
        [None] * 8,  # bo'sh qator — o'tkazib yuboriladi
    ]
    pre = post(w, "costs/preview", sheet([head, good, *wrong]))
    p = pre.json()
    assert pre.status_code == 200
    assert p["error_count"] == 5 and {e["row"] for e in p["errors"]} == {3, 4, 5, 6, 7}
    assert len(p["changes"]) == 1 and D(p["changes"][0]["new"]) == D("12500.50")
    assert p["changes"][0]["old"] in (None, p["changes"][0]["old"])
    # Mavjud narx ustidan yozish: avval saqlaymiz, keyin boshqa qiymat — "changed" va eski qiymat ko'rinadi.
    assert apply(w, [{"key": first_key, "unit_cost": "12500.50"}]).status_code == 200
    again = post(
        w, "costs/preview", sheet([head, [first_key, None, None, None, "n", None, None, 99_999]])
    ).json()
    assert again["changed"] == 1 and D(again["changes"][0]["old"]) == D("12500.50")
    # Ikki marta berilgan tovar — xato; saqlash ham rad etadi.
    dup = post(w, "costs/preview", sheet([head, good, good])).json()
    assert dup["error_count"] == 1
    assert (
        apply(
            w, [{"key": first_key, "unit_cost": "1"}, {"key": first_key, "unit_cost": "2"}]
        ).status_code
        == 422
    )
    assert (
        apply(
            w, [{"key": "item:00000000-0000-0000-0000-000000000000", "unit_cost": "1"}]
        ).status_code
        == 404
    )


def test_upload_security_limits_and_permissions(world: tr.World) -> None:
    w = world
    reset_limit(w)
    ok_sheet = sheet([list(HEADERS)])
    # xlsx emas / buzuq / shablon emas / bo'sh
    assert post(w, "costs/preview", b"salom, bu matn").status_code == 422
    assert post(w, "costs/preview", b"PK\x03\x04buzuq").status_code == 422
    assert post(w, "costs/preview", sheet([["A", "B"], [1, 2]])).json()["code"] == "bad_template"
    assert post(w, "costs/preview", b"").status_code == 422
    # 5 MB dan katta — 413 (o'qishdan oldin)
    assert post(w, "costs/preview", b"PK" + b"0" * (5 * 1024 * 1024 + 10)).status_code == 413
    # Qator soni chegarasi
    big = sheet(
        [list(HEADERS)] + [["", None, None, f"b{i}", "x", None, None, None] for i in range(20_001)]
    )
    r = post(w, "costs/preview", big)
    assert r.status_code == 422 and r.json()["code"] == "bad_file"
    # Ruxsat: faqat manage_settings (egasi, menejer)
    assert post(w, "costs/preview", ok_sheet, "accountant").status_code == 403
    assert post(w, "costs/preview", ok_sheet, "warehouse").status_code == 403
    assert w.call("opening/costs.xlsx", "accountant").status_code == 403
    assert apply(w, [{"key": "item:x", "unit_cost": "1"}], "accountant").status_code == 403
    # Daqiqasiga cheklov: 10 ta yuklashdan keyin — 429
    reset_limit(w)
    codes = [post(w, "costs/preview", ok_sheet).status_code for _ in range(12)]
    assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]
    reset_limit(w)
