# Pokémon restock alerts

Checks Dutch Pokémon webshops every ~5 minutes and sends a Telegram message when a Pokémon
product is new, back in stock, or (watchlist.yaml) at or below your max price. Alerts only, no buying.

- Shops: `shops.yaml` (Shopify or WooCommerce shops with a public product list)
- Price alerts: `watchlist.yaml`
- Runs on GitHub Actions (`.github/workflows/monitor.yml`); secrets `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID`
- Local test: `python monitor.py --dry-run`

## Big shops: what works (checked 2026-10-09)

| shop | result | how / why not |
|---|---|---|
| MediaMarkt | ✅ browser_watch.py (laptop) | Cloudflare refuses scripts and headless; a normal Chrome works; robots.txt allows the search page |
| Game Mania | ✅ browser_watch.py (laptop) | same as MediaMarkt (robots: `Allow: /`); no 30th cards on sale yet |
| Spellenvariant | ✅ browser_watch.py (laptop) | robots.txt forbids `/catalogsearch/`, allows sitemap + product pages -> opens the 30th product pages from the sitemap |
| Cees Cards | ✅ monitor.py (GitHub) | WooCommerce API answers a small search (`30th`, 50 per page); the big `pokemon` 100-per-page request gets 403 |
| Global Card Shop, Top1Toys | ✅ monitor.py (GitHub) | search page in plain HTML |
| Intertoys | ❌ | robots.txt for all bots: `Disallow: /search/*`, `/p/*` (products), `/c/*` (categories) |
| Kruidvat | ❌ | robots.txt: `Disallow: */search?*` and `*/search/*`; Akamai 403 for scripts |
| Bol | ❌ (official route possible) | robots.txt: `Disallow: /*/s/` (search); official route = Bol Partner Program API (needs a partner account) |
| Nedgame | ❌ | Cloudflare "Sorry, you have been blocked" also in a normal Chrome after a few automated page loads |
| Dreamland / Toychamp | ❌ | "Toegang geweigerd", then "Even controleren of je een mens bent" also in a normal Chrome (automated session) |

browser_watch.py: Windows task "Pokemon browser watch" every 10 min, off-screen Chrome, one search page (or the few
30th product pages) per shop per run, stops for that run when a shop shows a block or human check. Laptop must be on.
