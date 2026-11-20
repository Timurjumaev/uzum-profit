# Uzum MCP server (lokal, faqat o'qish)

Claude (Desktop yoki Code) shu serverga Mac'ingizda ulanadi va kabinetni tahlil qiladi. Kalit faqat shu
jarayonda qoladi — chatga, repozitoriyga yoki bulutga chiqmaydi. Faqat GET so'rovlari.

## O'rnatish (bir marta)

```bash
cd ~/uzum-profit   # repozitoriy papkasi
python3 -m venv ~/.uzum-mcp-venv && ~/.uzum-mcp-venv/bin/pip install "mcp>=1.2"
```

## Claude Desktop'ga ulash

`~/Library/Application Support/Claude/claude_desktop_config.json` ga qo'shing (yo'llarni o'zingiznikiga almashtiring):

```json
{
  "mcpServers": {
    "uzum": {
      "command": "/Users/SIZNING_ISMINGIZ/.uzum-mcp-venv/bin/python",
      "args": ["/Users/SIZNING_ISMINGIZ/uzum-profit/scripts/uzum_mcp_server.py"],
      "env": { "UZUM_API_KEY": "SHU_YERGA_KALIT" }
    }
  }
}
```

Kalitni konfigga yozmasangiz — repozitoriy ildizidagi `.env` (`UZUM_API_KEY=...`) o'qiladi. Claude Desktop'ni
qayta ishga tushiring. Kalit uchun "Faqat o'qish" ruxsati yetarli.

Claude Code uchun: `claude mcp add uzum -- ~/.uzum-mcp-venv/bin/python ~/uzum-profit/scripts/uzum_mcp_server.py`

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

## Eslatma

- "Foyda" — Uzum `sellerProfit` (tushum − komissiya − logistika), **tannarxsiz**. Tannarxli sof foyda — yangi tizimda.
- Uzum limiti ~2 so'rov/s: birinchi so'rov (butun tarix) ~daqiqa olishi mumkin, keyingilari keshdan.
- Chet el IP'dan Uzum WAF 403 beradi — server O'zbekistondagi Mac'da ishlaydi.
- Maydon nomlari real javobga moslab o'zgartirilishi mumkin; noto'g'ri chiqsa `api_get` bilan xom javobni ko'rib, menga yozing.
