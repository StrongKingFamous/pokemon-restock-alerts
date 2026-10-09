# Pokémon restock alerts

Checks Dutch Pokémon webshops every ~5 minutes and sends a Telegram message when a Pokémon
product is new, back in stock, or (watchlist.yaml) at or below your max price. Alerts only, no buying.

- Shops: `shops.yaml` (Shopify or WooCommerce shops with a public product list)
- Price alerts: `watchlist.yaml`
- Runs on GitHub Actions (`.github/workflows/monitor.yml`); secrets `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID`
- Local test: `python monitor.py --dry-run`

## Coverage (checked 2026-10-09)

Source list: tcgsniper.nl/winkels (102 shops). Every read path is checked against the shop's robots.txt
**with `*` wildcards** (Python's urllib.robotparser ignores them, which once gave wrong "allowed" answers).

- **monitor.py on GitHub (64 shops):** Shopify/WooCommerce product lists, plus `type: search` = one search or
  category page in plain HTML (product tiles found around links that mention 30th).
- **browser_watch.py on the laptop (3 shops):** a real Chrome, because these refuse scripts and headless browsers.
  - Game Mania: search page (robots: `Allow: /`).
  - MediaMarkt: search is forbidden (`Disallow: /*query=`), so the 30th product pages are found in the sitemap
    (once a day, ~2.5 min) and opened each run.
  - Spellenvariant: search is forbidden (`/catalogsearch/`), so the same sitemap + product pages route.

| not included | why |
|---|---|
| Intertoys | robots.txt: `Disallow: /search/*`, `/p/*`, `/c/*` |
| Kruidvat | robots.txt: `Disallow: */search?*`, `*/search/*`; Akamai 403 for scripts |
| Bol | robots.txt: `Disallow: /*/s/`; official route = Bol Partner Program API (needs a partner account) |
| Lobbes | robots.txt: `Disallow: */zoek/*` |
| Gameshop Twente | robots.txt forbids `/catalogsearch/` and every URL with `?`; no sitemap; category page shows no 30th |
| TCGino | robots.txt: `Disallow: /*?q=` |
| PKMkaarten | robots.txt: `Disallow: /*?` (the WooCommerce API needs a query string) |
| Mystery Media | robots.txt: `Disallow: /wp-json/` |
| Nerdgeek, Panini Belgium | robots.txt forbids their search page |
| Nedgame | Cloudflare "Sorry, you have been blocked", also in a normal Chrome after a few automated loads |
| Dreamland / Toychamp | "Toegang geweigerd", then a human check, also in a normal Chrome |
| Proshop | "Even geduld..." challenge page in a normal Chrome |
| Catch Your Cards, Dracoon | search page blocked, also in a normal Chrome |
| Chaos Cards (UK), Games Island (DE) | search only in a JavaScript pop-up; not built |
| Pokémon Center | Datadome/Imperva; US shop |
| Cardmarket | marketplace; API only for sellers |
| pokecardshop.nl, tcgcards.nl, gamebirds.nl, ... | domain for sale / no shop / not a Pokémon shop |

browser_watch.py runs as Windows task "Pokemon browser watch" every 10 min (off-screen Chrome, 15 min limit).
It stops for that run when a shop shows a block or human check. The laptop must be on.
