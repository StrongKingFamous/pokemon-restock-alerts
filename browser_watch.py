"""30th alerts for big shops that only answer a real browser (runs on the laptop, not on GitHub).

MediaMarkt and Game Mania refuse plain scripts and headless browsers, but answer a normal visible Chrome,
and their robots.txt allows the search page. Every run: per shop one home page + ONE search page, read the
product tiles, compare with browser_state.json and send the same 🎯 Telegram messages as monitor.py.
If a shop shows a block or "are you human" page, it is skipped and NOT retried until the next run.

    python browser_watch.py             (Windows task "Pokemon browser watch", every 10 min)
    python browser_watch.py --dry-run   (prints instead of sending)
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
from pathlib import Path

import sys

HERE = Path(__file__).resolve().parent
if sys.stdout is None:   # started by the Windows task with pythonw (no console): log to a file
    sys.stdout = sys.stderr = open(HERE / "browser_watch.log", "a", encoding="utf-8")

import yaml
from playwright.sync_api import sync_playwright

import monitor

STATE = HERE / "browser_state.json"
BLOCKED = re.compile(r"you have been blocked|attention required|toegang geweigerd|even controleren|verify you are human|"
                     r"access denied|captcha", re.I)
NOT_NOW = re.compile(r"geen bezorging|niet (meer )?(beschikbaar|leverbaar|op voorraad)|uitverkocht|sold out|"
                     r"pre\s*-?\s*order|binnenkort|verwacht", re.I)
EURO = re.compile(r"€\s?(\d{1,4}(?:\.\d{3})*,\d{2})")
SHOPS = [   # url = search page (allowed by the shop's robots.txt, checked 2026-10-09); item = CSS of one product tile
    {"name": "MediaMarkt", "home": "https://www.mediamarkt.nl",
     "url": "https://www.mediamarkt.nl/nl/search.html?query=pokemon%2030th", "item": "[data-test='mms-product-card']"},
    {"name": "Game Mania", "home": "https://www.gamemania.nl",
     "url": "https://www.gamemania.nl/catalogsearch/result/?q=pokemon+30th", "item": "li.product-item, .product-item-info"},
]


def load_env():
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def read_shop(pg, shop) -> list[dict] | None:
    pg.goto(shop["home"], timeout=30000)
    pg.wait_for_timeout(3000)
    pg.goto(shop["url"], timeout=30000)
    pg.wait_for_timeout(7000)
    if BLOCKED.search(pg.title() + " " + pg.inner_text("body")[:800]):
        return None
    out, seen = [], set()
    for tile in pg.query_selector_all(shop["item"]):
        text = re.sub(r"\s+", " ", tile.inner_text())
        link = tile.evaluate("e => { const a = [...e.querySelectorAll('a[href]')].find(a => a.innerText.trim()); "
                             "return a ? [a.href, a.innerText.trim()] : null; }")
        if not link or link[0] in seen:
            continue
        seen.add(link[0])
        prices = [float(p.replace(".", "").replace(",", ".")) for p in EURO.findall(text)]
        out.append({"id": link[0].split("?")[0], "title": link[1], "text": text, "url": link[0],
                    "price": min(prices) if prices else 0.0, "available": not NOT_NOW.search(text)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    dry = ap.parse_args().dry_run
    load_env()
    lists = yaml.safe_load((HERE / "watchlist.yaml").read_text(encoding="utf-8")) or {}
    focus, msrp = lists.get("focus") or [], lists.get("msrp") or {}
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    sent = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=False,
                                     args=["--window-position=-2400,0", "--window-size=1280,900"])   # off-screen
        pg = browser.new_page()
        for shop in SHOPS:
            name = shop["name"]
            try:
                products = read_shop(pg, shop)
            except Exception as e:
                print(f"{name}: skipped ({str(e)[:80]})")
                continue
            if products is None:
                print(f"{name}: block page shown, skipped this run")
                continue
            products = [p for p in products if monitor.focus_hit(p, focus)]
            print(f"{name}: {len(products)} 30th products, {sum(p['available'] for p in products)} available")
            old = state.get(name)
            if old is not None:
                for p in products:
                    before = old.get(p["id"])
                    f = monitor.focus_hit(p, focus)
                    tag = f"🎯 <b>{html.escape(f['name'])}</b> · "
                    link = f"<a href=\"{p['url']}\">{html.escape(p['title'])}</a>"
                    price = f"€{p['price']:.2f}".replace(".", ",") if p["price"] else "prijs nog onbekend"
                    ref = monitor.msrp_line(p, f["name"], msrp)
                    ref = f"\n<i>{ref}</i>" if ref else ""
                    if before is None:
                        txt = "nu te koop" if p["available"] else "nog niet online leverbaar"
                        monitor.send(f"{tag}🆕 Nieuw bij {name} ({txt})\n{link}\n{price}{ref}", dry); sent += 1
                    elif not before["a"] and p["available"]:
                        monitor.send(f"{tag}✅ Weer leverbaar bij {name}\n{link}\n{price}{ref}", dry); sent += 1
                    elif before["a"] and not p["available"]:
                        monitor.send(f"{tag}❌ Niet meer leverbaar bij {name}\n{link}", dry); sent += 1
                    elif p["available"] and before.get("p") and abs(before["p"] - p["price"]) >= 0.01:
                        old_price = f"€{before['p']:.2f}".replace(".", ",")
                        monitor.send(f"{tag}💶 Prijs {old_price} → {price} bij {name}\n{link}{ref}", dry); sent += 1
            state[name] = {p["id"]: {"a": p["available"], "p": p["price"]} for p in products}
        browser.close()
    if not dry:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    print(f"{sent} alerts")


if __name__ == "__main__":
    main()
