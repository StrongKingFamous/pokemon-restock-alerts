"""Pokémon TCG restock alerts for Dutch webshops -> Telegram.

Every run (GitHub Actions, every ~5 minutes) reads the public product lists of the shops in
shops.yaml, keeps only Pokémon products, and compares them with the previous run (state.json):

  * NEW       a Pokémon product that wasn't in the shop before (and is in stock)
  * RESTOCK   a product that was sold out and is available again
  * PRICE     a product on your watchlist (watchlist.yaml) at or below your max price

Only alerts, never buying: you click the link and decide yourself.
The very first run per shop only saves what's there (no flood of "new" messages).

Run locally:  python monitor.py --dry-run     (prints instead of sending)
Secrets:      TELEGRAM_TOKEN and TELEGRAM_CHAT_ID as environment variables (GitHub: repository secrets)
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
import yaml

HERE = Path(__file__).resolve().parent
STATE = HERE / "state.json"
UA = {"User-Agent": "Mozilla/5.0 (personal Pokémon restock alert; one request per page, every 5 min)"}
POKEMON = re.compile(r"pok[eé]mon", re.I)
SKIP = re.compile(r"\b(sleeves?|deck ?box|binder(?! collection)|map|toploader|playmat|speelmat|portfolio|kaarthouder|dice|dobbelste)", re.I)
PAUSE = 1.0           # seconds between requests to the same shop: be a polite visitor
MAX_PAGES = 15

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def shopify(base: str) -> list[dict]:
    out = []
    for page in range(1, MAX_PAGES + 1):
        r = requests.get(f"{base}/products.json", params={"limit": 250, "page": page}, headers=UA, timeout=30)
        r.raise_for_status()
        items = r.json().get("products", [])
        for p in items:
            text = " ".join([p.get("title", ""), p.get("product_type", ""), " ".join(p.get("tags") or [])])
            variants = p.get("variants") or [{}]
            out.append({
                "id": str(p["id"]), "title": p.get("title", ""), "text": text,
                "price": min(float(v.get("price") or 0) for v in variants),
                "available": any(v.get("available") for v in variants),
                "url": f"{base}/products/{p.get('handle')}",
            })
        if len(items) < 250:
            break
        time.sleep(PAUSE)
    return out


def woocommerce(base: str) -> list[dict]:
    out = []
    for page in range(1, MAX_PAGES + 1):
        r = requests.get(f"{base}/wp-json/wc/store/v1/products",
                         params={"per_page": 100, "page": page, "search": "pokemon"}, headers=UA, timeout=30)
        if r.status_code == 400:   # past the last page
            break
        r.raise_for_status()
        items = r.json()
        for p in items:
            pr = p.get("prices") or {}
            unit = int(pr.get("currency_minor_unit") or 2)
            cats = " ".join(c.get("name", "") for c in p.get("categories") or [])
            out.append({
                "id": str(p["id"]), "title": html.unescape(p.get("name", "")), "text": f"{p.get('name', '')} {cats}",
                "price": int(pr.get("price") or 0) / 10 ** unit,
                "available": bool(p.get("is_in_stock")) and bool(p.get("is_purchasable", True)),
                "url": p.get("permalink", base),
            })
        if len(items) < 100:
            break
        time.sleep(PAUSE)
    return out


NOT_NOW = re.compile(r"uitverkocht|niet (op voorraad|leverbaar)|out of stock|sold out|pre\s*-?\s*order|binnenkort|"
                     r"verwacht|coming soon", re.I)
EURO = re.compile(r"(\d{1,4}(?:\.\d{3})*,\d{2})")


def search(url: str, item: str) -> list[dict]:
    """Shops without a public product list: read ONE search-results page (plain HTML, no browser).
    item = CSS selector of one product tile. Title/link = first text link, price = lowest euro amount
    (sale price), available = no 'sold out' / 'pre-order' words in the tile."""
    from bs4 import BeautifulSoup
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    out, seen = [], set()
    for tile in BeautifulSoup(r.text, "html.parser").select(item):
        link = next((a for a in tile.find_all("a", href=True)
                     if a.get_text(strip=True) and "category" not in a["href"]), None)
        if not link or link["href"] in seen:
            continue
        seen.add(link["href"])
        text = re.sub(r"\s+", " ", tile.get_text(" "))
        prices = [float(p.replace(".", "").replace(",", ".")) for p in EURO.findall(text)]
        out.append({"id": link["href"], "title": link.get_text(" ", strip=True), "text": text,
                    "price": min(prices) if prices else 0.0, "available": not NOT_NOW.search(text),
                    "url": requests.compat.urljoin(url, link["href"])})
    return out


READERS = {"shopify": shopify, "woocommerce": woocommerce}


def is_pokemon_product(p: dict) -> bool:
    return bool(POKEMON.search(p["text"]) or POKEMON.search(p["title"])) and not SKIP.search(p["title"])


def send(text: str, dry: bool) -> None:
    if dry:
        print("  [telegram]", text.replace("\n", " | "))
        return
    token, chat = os.environ["TELEGRAM_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=20,
                  data={"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "false"})
    time.sleep(0.5)


SEALED = re.compile(r"booster|bundle|bundel|box|etb|elite trainer|collection|collectie|tin\b|blister|display|"
                    r"\bpack\b|\bcase\b|checklane|premium|sealed|doos|mini tin|build ?& ?battle", re.I)
SINGLE = re.compile(r"\b\d{1,3}/\d{2,3}\b|\bsingle\b|losse kaart|\bpsa\b|\bcgc\b|\bbgs\b|graded|\bholo\b rare|"
                    r"figure|figuur|plush|knuffel|beeldje", re.I)   # not sealed card products


def focus_hit(p: dict, focus: list[dict]) -> dict | None:
    """Focus lists (watchlist.yaml): every event for these products, also pre-orders, sold out and price changes."""
    t = p["title"].lower()
    for f in focus:
        if all(k.lower() in t for k in f.get("keywords", [])) and \
                (not f.get("any") or any(k.lower() in t for k in f["any"])) and \
                (not f.get("sealed_only") or (SEALED.search(t) and not SINGLE.search(t))):
            return f
    return None


def msrp_line(p: dict, focus_name: str, msrp: dict) -> str:
    """Official reference price for a focus product, if known (US MSRP / UK RRP; no official euro price)."""
    t = p["title"].lower()
    if re.search(r"chin|japan|korea|\bjp\b|\bcn\b|\bkr\b|\(jap|\bthai", t):   # other editions have other official prices
        return ""
    if re.search(r"display|\bcase\b|\d+\s?x\b|\d+\s?pc|\d+\s?stuks|set van|bundel van|combi", t):   # multiples
        return ""
    for m in msrp.get(focus_name) or []:
        if all(k in t for k in m["keywords"]) and not any(n in t for n in m.get("not", [])):
            parts = [f"${m['usd']:.2f} VS"] + ([f"£{m['gbp']:.2f} VK"] if m.get("gbp") else [])
            return "Officiële prijs: " + " / ".join(parts).replace(".", ",")
    return ""


def watch_hit(p: dict, watch: list[dict]) -> dict | None:
    t = p["title"].lower()
    for w in watch:
        if all(k.lower() in t for k in w["keywords"]) and p["price"] and p["price"] <= w["max_price"]:
            return w
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print the alerts instead of sending them")
    ap.add_argument("--overview", metavar="FOCUS", help="send what is in stock now for a focus list (no state change)")
    args = ap.parse_args()
    dry = args.dry_run
    shops = yaml.safe_load((HERE / "shops.yaml").read_text(encoding="utf-8"))["shops"]
    lists = yaml.safe_load((HERE / "watchlist.yaml").read_text(encoding="utf-8")) or {}
    watch, focus, msrp = lists.get("watch") or [], lists.get("focus") or [], lists.get("msrp") or {}
    only_focus = bool(lists.get("only_focus"))   # true: no alerts for other Pokémon products
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    sent = 0
    def fetch(shop):   # each shop is still read page by page (polite); different shops run at the same time
        try:
            if shop["type"] == "search":   # the search query already asks for Pokémon
                return shop, [p for p in search(shop["url"], shop["item"]) if not SKIP.search(p["title"])], None
            return shop, [p for p in READERS[shop["type"]](shop["url"].rstrip("/")) if is_pokemon_product(p)], None
        except Exception as e:   # one shop down must not stop the others
            return shop, None, e

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(fetch, shops))
    if args.overview:   # one-off summary of what is buyable right now
        f = [x for x in focus if x["name"] == args.overview]
        rows = sorted(((p["price"], shop["name"], p) for shop, products, err in results if products
                       for p in products if p["available"] and focus_hit(p, f)), key=lambda r: (r[2]["title"], r[0]))
        lines = [f"🎯 <b>{html.escape(args.overview)}: nu op voorraad ({len(rows)})</b>"]
        for price, shop_name, p in rows:
            euro = f"€{price:.2f}".replace(".", ",")
            ref = msrp_line(p, args.overview, msrp).replace("Officiële prijs: ", "officieel ")
            lines.append(f"• <a href=\"{p['url']}\">{html.escape(p['title'][:70])}</a> · {shop_name} · {euro}"
                         + (f" ({ref})" if ref else ""))
        msg = ""
        for line in lines:   # Telegram messages max 4096 characters
            if len(msg) + len(line) > 3800:
                send(msg, dry); msg = ""
            msg += line + "\n"
        send(msg or lines[0], dry)
        return
    for shop, products, err in results:
        name = shop["name"]
        if err is not None:
            print(f"{name}: skipped ({str(err)[:80]})")
            continue
        old = state.get(name)
        new_state = {p["id"]: {"a": p["available"], "p": p["price"], "w": (old or {}).get(p["id"], {}).get("w")}
                     for p in products}
        print(f"{name}: {len(products)} Pokémon products, {sum(p['available'] for p in products)} in stock")
        if old is not None:   # first run per shop only records what's there
            for p in products:
                before = old.get(p["id"])
                price = f"€{p['price']:.2f}".replace(".", ",") if p["price"] else "prijs nog onbekend"
                link = f"<a href=\"{p['url']}\">{html.escape(p['title'])}</a>"
                f = focus_hit(p, focus)
                if f:   # focus product: every event
                    tag = f"🎯 <b>{html.escape(f['name'])}</b> · "
                    ref = msrp_line(p, f["name"], msrp)
                    ref = f"\n<i>{ref}</i>" if ref else ""
                    new_price, price = price, price + ref
                    if before is None:
                        state_txt = "nu te koop" if p["available"] else "nog niet leverbaar (pre-order/binnenkort)"
                        send(f"{tag}🆕 Nieuw bij {name} ({state_txt})\n{link}\n{price}", dry); sent += 1
                    elif not before["a"] and p["available"]:
                        send(f"{tag}✅ Weer op voorraad bij {name}\n{link}\n{price}", dry); sent += 1
                    elif before["a"] and not p["available"]:
                        send(f"{tag}❌ Uitverkocht bij {name}\n{link}", dry); sent += 1
                    elif before["a"] and p["available"] and abs((before.get("p") or 0) - p["price"]) >= 0.01:
                        old_price = f"€{before['p']:.2f}".replace(".", ",")
                        send(f"{tag}💶 Prijs {old_price} → {new_price} bij {name}\n{link}{ref}", dry); sent += 1
                    continue
                if only_focus:
                    continue
                if before is None and p["available"]:
                    send(f"🆕 <b>Nieuw</b> bij {name}\n{link}\n{price}", dry); sent += 1
                elif before is not None and not before["a"] and p["available"]:
                    send(f"✅ <b>Weer op voorraad</b> bij {name}\n{link}\n{price}", dry); sent += 1
                w = watch_hit(p, watch) if p["available"] else None
                if w and (before or {}).get("w") != p["price"]:   # once per price
                    send(f"💰 <b>Onder je max (€{w['max_price']})</b> bij {name}\n{link}\n{price}", dry); sent += 1
                    new_state[p["id"]]["w"] = p["price"]
        state[name] = new_state
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    print(f"{sent} alerts")


if __name__ == "__main__":
    main()
