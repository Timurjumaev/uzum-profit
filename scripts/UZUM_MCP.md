# Uzum MCP server (lokal, faqat o'qish)

Claude (Desktop yoki Code) shu serverga Mac'ingizda ulanadi va kabinetni tahlil qiladi. Kalit faqat shu
jarayonda qoladi — chatga, repozitoriyga yoki bulutga chiqmaydi. Faqat GET so'rovlari.

Bu — **shaxsiy vosita** (reja tashqarisida). Sotuvchilar uchun MCP — rejadagi B10 nomzodi, ADR-072 taklifi.

## O'rnatish (bir marta)

Kerak: [`uv`](https://docs.astral.sh/uv/). Yo'q bo'lsa (skript `astral.sh` dan yuklanadi, `sudo` kerak emas),
keyin yangi terminal oching:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```bash
cd ~/Projects/uzum-profit   # repozitoriy qayerda bo'lsa, o'sha papka
uv venv --python 3.13 ~/.uzum-mcp-venv
uv pip install --python ~/.uzum-mcp-venv/bin/python --only-binary cryptography "mcp>=1.2"
```

**Nega Python 3.13 va `--only-binary`:** tizim Python'i 3.15 yoki Mac Intel bo'lsa, `mcp` ning `cryptography`
bog'liqligi uchun tayyor paket topilmaydi; `pip` uni Rust bilan yig'moqchi bo'lib yiqiladi
(`Failed building wheel for cryptography`). `--only-binary` tayyor paketi bor versiyani tanlatadi.

**Kalit:** repozitoriy ildizidagi `.env` ga (git'ga kirmaydi). Terminal tarixiga qoldirmaslik uchun:

```bash
read -s "k?Uzum kaliti (ko'rinmaydi): " && printf 'UZUM_API_KEY=%s\n' "$k" > .env && unset k && chmod 600 .env
```

Kalit uchun "Faqat o'qish" ruxsati yetarli. (Bu buyruq `.env` ni **almashtiradi** — fayl bor bo'lsa qo'lda qo'shing.)

## Claude Code'ga ulash

```bash
cd ~/Projects/uzum-profit
claude mcp add uzum -- ~/.uzum-mcp-venv/bin/python ~/Projects/uzum-profit/scripts/uzum_mcp_server.py
```

`claude` ni shu papkada qayta oching (MCP faqat shu loyiha papkasida ishlaydi), `/mcp` da `uzum` — `connected`.

## Claude Desktop'ga ulash

`~/Library/Application Support/Claude/claude_desktop_config.json` ga (yo'llarni o'zingizniki bilan almashtiring):

```json
{
  "mcpServers": {
    "uzum": {
      "command": "/Users/SIZNING_ISMINGIZ/.uzum-mcp-venv/bin/python",
      "args": ["/Users/SIZNING_ISMINGIZ/Projects/uzum-profit/scripts/uzum_mcp_server.py"]
    }
  }
}
```

Kalit `.env` dan o'qiladi. Claude Desktop'ni qayta ishga tushiring.

## Asboblar

| Asbob | Nima beradi |
|---|---|
| `shops` | do'konlar va id'lari |
| `sales_summary` | tushum, komissiya, logistika, Uzum foydasi — kun/hafta/oy/tovar/holat bo'yicha |
| `orders` | alohida sotuv qatorlari (holat, tovar qidiruvi) |
| `expenses_summary` | xarajatlar kod/oy/nom bo'yicha (saqlash, reklama, jarima...) |
| `products` | SKU: narx, qoldiq, sotilgan, qaytgan, brak; kam qoldiqni saralash |
| `invoices`, `returns` | FBO postavkalar, qaytarishlar |
| `api_get` | boshqa endpointlar uchun xom GET (FBS va h.k.) |
| `clear_cache` | keshni tozalash (standart 10 daqiqa, `UZUM_MCP_CACHE` bilan o'zgaradi) |

Misol savollar: "byDurii'ning oxirgi 60 kunlik foydasini haftalar bo'yicha ko'rsat", "qaysi tovarlar eng
ko'p qaytgan?", "qoldig'i 5 dan kam tovarlar", "bu oy xarajatlar nimaga ketdi?".

## Tekshirilgan natijalar (2026-11-21, Temurning Mac'ida, real kalit)

| Asbob | Holat |
|---|---|
| `shops` | tekshirilgan: ikkala do'kon (byDurii, EL-ONE) chiqdi |
| `sales_summary` | tekshirilgan: tushum va dona SellerMax bilan mos (bugun — raqamma-raqam; oy — ikkala do'kon qo'shilganda) |
| `orders`, `expenses_summary`, `products`, `invoices`, `returns` | hali tekshirilmagan |

Tekshirilmagan asboblar natijasiga ishonishdan oldin SellerMax yoki Uzum kabinetidagi raqam bilan solishtiring.

## Eslatma

- "Foyda" — Uzum `sellerProfit` (tushum − komissiya − logistika), **tannarxsiz**. Tannarxli sof foyda — yangi tizimda.
- Uzum limiti ~2 so'rov/s: birinchi so'rov (butun tarix) ~daqiqa olishi mumkin, keyingilari keshdan.
- Chet el IP'dan Uzum WAF 403 beradi — server O'zbekistondagi Mac'da ishlaydi.
- Maydon nomlari real javobga moslab o'zgartirilishi mumkin; noto'g'ri chiqsa `api_get` bilan xom javobni ko'rib, xabar bering.
