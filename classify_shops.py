"""One-off: for shops without a Shopify/WooCommerce product list, find out whether they block us and
which shop system they run (so we know which can be read politely).

    python classify_shops.py domains.txt
"""
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

UA = {"User-Agent": "Mozilla/5.0 (personal Pokémon restock alert; one request per page, every 10 min)"}
SIGNS = [
    ("blocked: bot wall", r"just a moment|cf-chl|challenge-platform|captcha|access denied|datadome|perimeterx|incapsula"),
    ("lightspeed", r"webshopapp|lightspeedhq|seoshop"),
    ("woocommerce (API off)", r"wp-content|woocommerce"),
    ("magento", r"mage/|magento"),
    ("shopware", r"shopware"),
    ("prestashop", r"prestashop"),
    ("ccv shop", r"ccvshop"),
    ("mijnwebwinkel", r"mijnwebwinkel"),
    ("wix", r"wix\.com|wixstatic"),
    ("squarespace", r"squarespace"),
    ("shopify (list off)", r"cdn\.shopify|shopify"),
]


def classify(domain: str):
    try:
        r = requests.get(f"https://{domain}", headers=UA, timeout=20, allow_redirects=True)
    except Exception as e:
        return domain, "unreachable", str(e)[:50]
    body = r.text[:300000].lower()
    if r.status_code in (401, 403, 429) or (r.status_code == 503 and "challenge" in body):
        return domain, f"blocked ({r.status_code})", r.url
    for label, pat in SIGNS:
        if re.search(pat, body):
            return domain, label, r.url
    return domain, f"other ({r.status_code})", r.url


if __name__ == "__main__":
    domains = [d.strip() for d in open(sys.argv[1], encoding="utf-8") if d.strip()]
    with ThreadPoolExecutor(12) as ex:
        rows = list(ex.map(classify, domains))
    for d, kind, url in sorted(rows, key=lambda r: r[1]):
        print(f"{kind:24} {d:28} {url}")
