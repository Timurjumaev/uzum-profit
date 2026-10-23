# -*- coding: utf-8 -*-
"""Partiya tannarxi (Temurning usuli) va SKU bo'yicha o'rtacha tannarx.

Usul (har bir partiya uchun):
  tovar narxi  = (tovar uchun to'langan CNY / dona) * CNY kursi          [o'sha kungi kurs]
  kargo        = (kargo USD / dona) * USD kursi                          [o'sha kungi kurs]
  qo'shimcha   = qo'shimcha chiqimlar yig'indisi (so'm) / dona
  tannarx      = tovar narxi + kargo + qo'shimcha
Agar qatorda "CNY narx" alohida yozilgan bo'lsa, shu narx ishlatiladi, qolgan
summa narx yozilmagan donalar o'rtasida teng bo'linadi.

Partiya bosqichma-bosqich to'ldiriladi:
  1) buyurtma: faqat tovar uchun CNY va CNY kursi (shart);
  2) mahsulot qatorlari: SKU yoki (kartochka hali yo'q bo'lsa) vaqtinchalik nom + soni;
  3) kargo (USD + kurs): narxi chiqqanda; cargo_usd NULL = "hali kiritilmagan";
  4) qo'shimcha chiqimlar;  5) nomi yozilgan qatorga keyinroq SKU biriktirish.
"""
import difflib


def load_batches(conn, shop_id=None):
    sql = "SELECT * FROM batches" + (" WHERE shop_id=?" if shop_id is not None else "") + " ORDER BY date, id"
    out = []
    for b in conn.execute(sql, (shop_id,) if shop_id is not None else ()):
        out.append(_with_children(conn, dict(b)))
    return out


def load_batch(conn, batch_id):
    row = conn.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
    return _with_children(conn, dict(row)) if row else None


def _with_children(conn, b):
    b["lines"] = [dict(r) for r in conn.execute(
        "SELECT * FROM batch_lines WHERE batch_id=? ORDER BY id", (b["id"],))]
    b["extras"] = [dict(r) for r in conn.execute(
        "SELECT * FROM batch_extras WHERE batch_id=? ORDER BY id", (b["id"],))]
    return b


def effective_date(batch):
    """Tannarx qaysi sanadan boshlab hisobga olinadi: kargo to'langan (tovar qo'lga olingan) sana,
    u yo'q bo'lsa buyurtma sanasi. Kargo sanasi buyurtma sanasidan oldin bo'lishi mumkin emas."""
    cargo_date = batch.get("cargo_date")
    return max(batch["date"], cargo_date) if cargo_date else batch["date"]


def batch_totals(batch):
    """Dona sonidan qat'i nazar, shu paytgacha sarflangan summalar (so'mda)."""
    goods = (batch.get("goods_cny") or 0) * (batch.get("cny_rate") or 0)
    cargo = (batch.get("cargo_usd") or 0) * (batch.get("usd_rate") or 0)
    extras = sum(e["amount"] for e in batch["extras"])
    return {"goods": goods, "cargo": cargo, "extras": extras, "total": goods + cargo + extras}


def batch_state(batch):
    """Partiya qaysi bosqichda ekanini ko'rsatadi."""
    lines = batch["lines"]
    units = sum(l["qty"] for l in lines)
    unlinked = [l for l in lines if not l.get("sku")]
    return {"units": units, "line_count": len(lines), "unlinked": len(unlinked),
            "no_lines": units == 0, "cargo_missing": batch.get("cargo_usd") is None,
            "complete": units > 0 and not unlinked and batch.get("cargo_usd") is not None}


def compute_batch(batch):
    """Partiya qatorlari bo'yicha 1 dona tannarxini hisoblaydi. Ro'yxat qaytaradi.
    SKU biriktirilmagan qatorlar ham hisoblanadi (ular ham partiya donalari)."""
    lines, extras = batch["lines"], batch["extras"]
    units = sum(l["qty"] for l in lines)
    if units <= 0:
        return []
    explicit = sum(l["qty"] * l["cny_unit"] for l in lines if l["cny_unit"] is not None)
    rest_units = sum(l["qty"] for l in lines if l["cny_unit"] is None)
    rest_per_unit = max((batch.get("goods_cny") or 0) - explicit, 0.0) / rest_units if rest_units else 0.0
    cargo = (batch.get("cargo_usd") or 0) / units * (batch.get("usd_rate") or 0)
    extra = sum(e["amount"] for e in extras) / units
    out = []
    for l in lines:
        cny_u = l["cny_unit"] if l["cny_unit"] is not None else rest_per_unit
        goods = cny_u * (batch.get("cny_rate") or 0)
        out.append({"sku": l.get("sku"), "label": l.get("label"), "name": l.get("sku") or l.get("label") or "—",
                    "qty": l["qty"], "cny_unit": cny_u, "goods": goods,
                    "cargo": cargo, "extras": extra, "unit_cost": goods + cargo + extra})
    return out


def batch_summary(batch):
    rows = compute_batch(batch)
    units = sum(r["qty"] for r in rows)
    total = sum(r["qty"] * r["unit_cost"] for r in rows)
    return {"units": units, "total": total, "avg": total / units if units else None, "rows": rows}


def batch_warnings(batch):
    """Kiritilgan ma'lumotlardagi shubhali joylar."""
    w, lines = [], batch["lines"]
    goods = batch.get("goods_cny") or 0
    explicit = sum(l["qty"] * l["cny_unit"] for l in lines if l["cny_unit"] is not None)
    if explicit > goods + 0.5:
        w.append("Qatorlardagi CNY narxlar yig'indisi umumiy summadan katta.")
    if lines and all(l["cny_unit"] is not None for l in lines) and abs(explicit - goods) > 1:
        w.append("Hamma qatorda narx yozilgan, lekin yig'indi umumiy summaga teng emas: "
                 "umumiy summa e'tiborga olinmaydi.")
    return w


def sku_options(conn, shop_id):
    """Do'kondagi barcha ma'lum SKU'lar: [(sku, mahsulot nomi, omborda qoldiq)] (mahsulotlar + sotuvlar)."""
    rows = conn.execute(
        "SELECT sku, MAX(title) AS title, MAX(stock) AS stock FROM ("
        " SELECT sku, title, qty_fbo AS stock FROM skus WHERE shop_id=?"
        " UNION ALL SELECT sku, title, NULL FROM order_items WHERE shop_id=? AND sku IS NOT NULL"
        ") WHERE sku IS NOT NULL AND sku != '' GROUP BY sku ORDER BY sku", (shop_id, shop_id)).fetchall()
    return [(r["sku"], r["title"] or "", r["stock"]) for r in rows]


def sku_catalog(conn, shop_id):
    """Do'kondagi barcha ma'lum SKU kodlari."""
    return [o[0] for o in sku_options(conn, shop_id)]


def match_sku(code, catalog):
    """Kod katta-kichik harfga e'tiborsiz moslanadi. (aniq_kod, takliflar) qaytaradi."""
    low = {c.lower(): c for c in catalog}
    if code.lower() in low:
        return low[code.lower()], []
    return None, difflib.get_close_matches(code, catalog, n=3, cutoff=0.6)


class CostBook:
    """SKU bo'yicha o'rtacha tannarx: sotuv sanasigacha qo'lga olingan partiyalarning vaznli o'rtachasi.
    Faqat SKU biriktirilgan qatorlar hisobga olinadi.

    Kargo narxi hali kiritilmagan partiya "yo'lda" hisoblanadi (kargo tovar qo'lga olinganda to'lanadi,
    ya'ni tovar hali kelmagan). SKU'ning boshqa to'liq partiyasi bo'lsa, yo'ldagi partiya tannarxga
    aralashmaydi: aks holda 20-25 kun davomida eski tovar sotuvlari noto'g'ri tannarx bilan hisoblanardi.
    Agar SKU'da faqat shunday partiya bo'lsa (sotuv bor, demak tovar kelgan), kargosiz tannarx olinadi
    va "nocargo" belgisi qo'yiladi."""

    def __init__(self, conn, shop_id):
        self.by_sku = {}
        for b in load_batches(conn, shop_id):
            eff, no_cargo = effective_date(b), b.get("cargo_usd") is None
            for r in compute_batch(b):
                if r["sku"]:
                    self.by_sku.setdefault(r["sku"].lower(), []).append((eff, r["qty"], r["unit_cost"], no_cargo))

    def unit_cost(self, sku, date):
        """(tannarx, belgilar). Belgilar: 'early' (sanagacha partiya bo'lmagan: hamma partiyalar olindi),
        'nocargo' (ishlatilgan partiyalardan birida kargo narxi hali kiritilmagan)."""
        rows = self.by_sku.get((sku or "").lower())
        if not rows:
            return None, set()
        before = [r for r in rows if r[0] <= date]
        pool = before or rows
        use = [r for r in pool if not r[3]] or pool          # yo'ldagi partiya faqat boshqa partiya bo'lmasa
        q = sum(r[1] for r in use)
        if q <= 0:
            return None, set()
        flags = set()
        if not before:
            flags.add("early")
        if any(r[3] for r in use):
            flags.add("nocargo")
        return sum(r[1] * r[2] for r in use) / q, flags
