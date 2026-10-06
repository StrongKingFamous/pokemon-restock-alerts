"""One-off: find out which shops have a readable public product list (Shopify / WooCommerce) and their currency.

    python probe_shops.py domains.txt   -> prints a shops.yaml-ready list
"""
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

UA = {"User-Agent": "Mozilla/5.0 (personal Pokémon restock alert; one request per page, every 10 min)"}


def probe(domain: str):
    for base in (f"https://{domain}", f"https://www.{domain}"):
        try:
            r = requests.get(f"{base}/products.json", params={"limit": 1}, headers=UA, timeout=15)
            if r.status_code == 200 and r.text.lstrip().startswith('{') and '"products"' in r.text:
                cur = "EUR"
                try:
                    cur = requests.get(f"{base}/cart.js", headers=UA, timeout=15).json().get("currency") or "EUR"
                except Exception:
                    pass
                return domain, "shopify", r.url.split("/products.json")[0], cur
            r = requests.get(f"{base}/wp-json/wc/store/v1/products", params={"per_page": 1}, headers=UA, timeout=15)
            if r.status_code == 200 and '"prices"' in r.text:
                data = r.json()
                cur = (data[0].get("prices") or {}).get("currency_code", "EUR") if data else "EUR"
                return domain, "woocommerce", r.url.split("/wp-json")[0], cur
        except Exception:
            continue
    return domain, None, None, None


if __name__ == "__main__":
    domains = [d.strip() for d in open(sys.argv[1], encoding="utf-8") if d.strip()]
    with ThreadPoolExecutor(12) as ex:
        for domain, kind, base, cur in ex.map(probe, domains):
            print(f"{'OK ' if kind else '-- '}{domain:28} {kind or ''} {base or ''} {cur or ''}")
