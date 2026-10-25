"""O'qish API'lari (B2.9; 03 §8): bosh sahifa, P&L, SKU, sotuvlar, xarajatlar, ombor — ``upcore`` ustida.

Bazadan faqat faktlar o'qiladi (``daily_sku_metrics``, ``sale_items`` + ``sale_costs``, ``mp_expenses``,
``manual_expenses``, ``tax_profiles``, lotlar, snapshotlar); hamma formula — ``upcore`` da (tamoyil 4). Marshrutlar
``upapi.routes`` da, umumiy qism shu paketda:

- :mod:`upapi.reports.common` — davr va do'kon filtri, ``meta.freshness``, sahifalash kursori;
- :mod:`upapi.reports.cells` — P&L kataklari (ADR-026), F16 bloki, "qayta hisoblandi" belgisi;
- :mod:`upapi.reports.stock` — ombor ko'rsatkichlari (F23–F30);
- :mod:`upapi.reports.schemas` — javob modellari (pul — satr, nisbat — kasr satr).
"""
