# Pokémon restock alerts

Checks Dutch Pokémon webshops every ~5 minutes and sends a Telegram message when a Pokémon
product is new, back in stock, or (watchlist.yaml) at or below your max price. Alerts only, no buying.

- Shops: `shops.yaml` (Shopify or WooCommerce shops with a public product list)
- Price alerts: `watchlist.yaml`
- Runs on GitHub Actions (`.github/workflows/monitor.yml`); secrets `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID`
- Local test: `python monitor.py --dry-run`
