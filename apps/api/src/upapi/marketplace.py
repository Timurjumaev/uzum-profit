"""Marketplace provayderi interfeysi (03 §6). Uzum — birinchi realizatsiya (:class:`upapi.uzum.client.UzumClient`);
Yandex, WB, Ozon keyin shu interfeys bilan qo'shiladi (M20, B10). FBS buyurtmalari — B5.

Sinxron ishlari (B2.6) faqat shu interfeysga tayanadi: sahifalar xom JSON bilan (``Page.raw``) qaytadi, maydonlarni
o'qish provayderga xos xaritalashda.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Any, Protocol

from upapi.uzum.client import Page


class ShopInfo(Protocol):
    @property
    def external_id(self) -> int: ...

    @property
    def name(self) -> str: ...


class MarketplaceProvider(Protocol):
    quota_remaining: int | None

    async def shops(self) -> Sequence[ShopInfo]: ...

    def orders(
        self,
        shop_id: int,
        date_from: datetime | int,
        date_to: datetime | int | None = None,
        **kw: Any,
    ) -> AsyncIterator[Page]: ...

    def expenses(
        self,
        shop_id: int,
        date_from: datetime | int,
        date_to: datetime | int | None = None,
        **kw: Any,
    ) -> AsyncIterator[Page]: ...

    def products(self, shop_id: int, **kw: Any) -> AsyncIterator[Page]: ...

    def invoices(self, shop_id: int, **kw: Any) -> AsyncIterator[Page]: ...

    def invoice_products(self, shop_id: int, invoice_id: int, **kw: Any) -> AsyncIterator[Page]: ...

    def returns(self, shop_id: int, **kw: Any) -> AsyncIterator[Page]: ...
