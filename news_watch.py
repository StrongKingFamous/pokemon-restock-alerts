"""Ticket-news alerts -> Telegram (⚽).

Watches club news pages listed in news.yaml and sends a message when a NEW article appears whose link
or title contains one of the keywords (e.g. a new ticket-sale phase for a match). Only reads the public
news page; the ticket shops themselves (with their queue systems) are left alone.

    python news_watch.py --dry-run
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
from urllib.parse import urljoin

import requests
import yaml

HERE = Path(__file__).resolve().parent
STATE = HERE / "news_state.json"
UA = {"User-Agent": "Mozilla/5.0 (personal ticket-news alert; one request every 5 min)"}

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def send(text: str, dry: bool) -> None:
    if dry:
        print("  [telegram]", text.replace("\n", " | "))
        return
    requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}/sendMessage", timeout=20,
                  data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text, "parse_mode": "HTML"})
    time.sleep(0.5)


def articles(src: dict) -> list[tuple[str, str]]:
    """(absolute url, title) of the article links on the news page."""
    page = requests.get(src["url"], headers=UA, timeout=30)
    page.raise_for_status()
    out, seen = [], set()
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page.text, re.S):
        href, inner = m.group(1), m.group(2)
        if src["link_contains"] not in href:
            continue
        url = urljoin(src["url"], href)
        title = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner))).strip()
        if url in seen or url.rstrip("/") == src["url"].rstrip("/"):
            continue
        seen.add(url)
        out.append((url, title or url.rsplit("/", 1)[-1].replace("-", " ")))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    dry = ap.parse_args().dry_run
    sources = (yaml.safe_load((HERE / "news.yaml").read_text(encoding="utf-8")) or {}).get("news") or []
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    sent = 0
    for src in sources:
        try:
            found = articles(src)
        except Exception as e:
            print(f"{src['name']}: skipped ({str(e)[:80]})")
            continue
        known = set(state.get(src["name"], []))
        first = src["name"] not in state
        for url, title in found:
            text = f"{url} {title}".lower()
            if url in known or not any(k in text for k in src["keywords"]):
                continue
            if not first or src.get("send_existing"):
                send(f"⚽ <b>{html.escape(src['label'])}</b>\n<a href=\"{url}\">{html.escape(title)}</a>", dry)
                sent += 1
        state[src["name"]] = sorted(known | {u for u, _ in found})
        print(f"{src['name']}: {len(found)} articles checked")
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{sent} news alerts")


if __name__ == "__main__":
    main()
