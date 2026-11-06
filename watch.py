#!/usr/bin/env python3
"""
iPhone Duo stock watcher for apple.com/ae
Default target: iPhone Duo 512GB Star White.

Checks two things on Apple UAE:
  1. In store pickup at Apple UAE stores (Dubai Mall, Mall of the Emirates, Yas Mall, Al Maryah Island)
  2. Online delivery quote (e.g. "Delivers Tue 10 Nov")

Sends an alert through ntfy.sh (free push app, no account) and/or Telegram.

Settings come from environment variables:
  NTFY_TOPIC          your private ntfy topic name (pick something hard to guess)
  TELEGRAM_BOT_TOKEN  optional, from @BotFather
  TELEGRAM_CHAT_ID    optional, your chat id
  PART_NUMBER         optional, force a part number (e.g. MK2F4AH/A) and skip auto discovery
  CAPACITY            default "512"
  COLOR               default "star white"
  LOCATIONS           default "Dubai,Abu Dhabi"
  ALERT_ON_DELIVERY   "1" (default) to also alert when online delivery becomes possible
  INTERVAL_SEC        if set (e.g. 5), loop forever and check every N seconds (for laptop use)
  INTERVAL_MIN        same, in minutes (older option)
  REALERT_SEC         while still in stock, repeat the alert at most this often (default 60)
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://www.apple.com/ae"
BUY_PAGES = [
    f"{BASE}/shop/buy-iphone/iphone-duo",
    f"{BASE}/shop/buy-iphone/iphone-duo/512gb-star-white",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept-Language": "en-AE,en;q=0.9",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
}

CAPACITY = os.getenv("CAPACITY", "512").lower().replace("gb", "")
COLOR = os.getenv("COLOR", "star white").lower()
LOCATIONS = [l.strip() for l in os.getenv("LOCATIONS", "Dubai,Abu Dhabi").split(",") if l.strip()]
ALERT_ON_DELIVERY = os.getenv("ALERT_ON_DELIVERY", "1") == "1"

UNAVAILABLE_WORDS = ("unavailable", "not available", "currently unavailable", "sold out")


def get(url, retries=2):
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"GET failed {url}: {last}")


# ---------- part number discovery ----------

def find_part_number(html):
    """Find the part number whose surrounding JSON mentions the wanted capacity and colour."""
    color_keys = {COLOR, COLOR.replace(" ", ""), COLOR.replace(" ", "-"), COLOR.replace(" ", "_")}
    cap_pat = re.compile(rf"{CAPACITY}\s*gb", re.I)
    hits = {}
    for m in re.finditer(r'"partNumber"\s*:\s*"([A-Z0-9]{5,}/[A-Z])"', html):
        part = m.group(1)
        window = html[max(0, m.start() - 800): m.end() + 800].lower()
        score = 0
        if cap_pat.search(window):
            score += 1
        if any(k in window for k in color_keys):
            score += 1
        if "duo" in window:
            score += 0.5
        hits[part] = max(hits.get(part, 0), score)
    good = [p for p, s in sorted(hits.items(), key=lambda x: -x[1]) if s >= 2]
    return good[0] if good else None


def discover_part():
    forced = os.getenv("PART_NUMBER", "").strip()
    if forced:
        return forced
    for url in BUY_PAGES:
        try:
            part = find_part_number(get(url))
            if part:
                print(f"[discover] {part} from {url}")
                return part
        except Exception as e:  # noqa: BLE001
            print(f"[discover] {e}")
    return None


# ---------- availability checks ----------

def check_pickup(part, location):
    q = urllib.parse.urlencode({
        "pl": "true", "mts.0": "regular", "mts.1": "compact",
        "parts.0": part, "location": location,
    })
    data = json.loads(get(f"{BASE}/shop/fulfillment-messages?{q}"))
    stores = (data.get("body", {}).get("content", {})
              .get("pickupMessage", {}).get("stores", []))
    available = []
    for s in stores:
        pa = (s.get("partsAvailability") or {}).get(part, {})
        status = (pa.get("pickupDisplay") or "").lower()
        msg = pa.get("pickupSearchQuote") or pa.get("storePickupQuote") or ""
        if status == "available":
            available.append(f"{s.get('storeName', '?')}: {strip_tags(msg)}")
    return available, data


def check_delivery(part):
    q = urllib.parse.urlencode({"parts.0": part, "mts.0": "regular", "mts.1": "compact"})
    data = json.loads(get(f"{BASE}/shop/delivery-message?{q}"))
    dm = (data.get("body", {}).get("content", {})
          .get("deliveryMessage", {}).get(part, {}))
    buyable = dm.get("isBuyable")
    texts = []
    for k in ("regular", "compact"):
        block = dm.get(k) or {}
        for opt in block.get("deliveryOptions", []) or []:
            texts.append(opt.get("date") or opt.get("shippingCost") or "")
        for f in ("quote", "deliveryOptionMessages", "stickyMessageSTH"):
            v = block.get(f)
            if isinstance(v, str):
                texts.append(v)
            elif isinstance(v, list):
                texts += [x.get("displayName", "") if isinstance(x, dict) else str(x) for x in v]
    text = " | ".join(strip_tags(t) for t in texts if t)
    ok = bool(buyable) and text and not any(w in text.lower() for w in UNAVAILABLE_WORDS)
    return ok, text


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


# ---------- notifications ----------

def notify(title, body, url):
    sent = False
    topic = os.getenv("NTFY_TOPIC")
    if topic:
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}", data=body.encode(),
            headers={"Title": title, "Priority": "urgent", "Tags": "iphone,rotating_light",
                     "Click": url})
        urllib.request.urlopen(req, timeout=20)
        sent = True
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if token and chat:
        payload = urllib.parse.urlencode({"chat_id": chat, "text": f"{title}\n\n{body}\n{url}"}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, timeout=20)
        sent = True
    if not sent:
        print("[notify] no NTFY_TOPIC or Telegram set, printing only")
    print(f"ALERT: {title}\n{body}")


# ---------- main ----------

_PART_CACHE = None


def run_once():
    global _PART_CACHE
    part = _PART_CACHE or discover_part()
    _PART_CACHE = part
    if not part:
        print("Could not find the part number. Set PART_NUMBER (see README).")
        return 2
    buy_url = f"{BASE}/shop/buy-iphone/iphone-duo"
    found, errors = [], 0
    for loc in LOCATIONS:
        try:
            stores, _ = check_pickup(part, loc)
            found += stores
        except Exception as e:  # noqa: BLE001
            print(f"[pickup {loc}] {e}")
            errors += 1
    found = sorted(set(found))

    delivery_ok, delivery_text = False, ""
    try:
        delivery_ok, delivery_text = check_delivery(part)
    except Exception as e:  # noqa: BLE001
        print(f"[delivery] {e}")
        errors += 1
    if errors == len(LOCATIONS) + 1:
        raise RuntimeError("all checks failed (Apple may be blocking)")

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {part} pickup={found or 'none'} "
          f"delivery={'yes' if delivery_ok else 'no'} ({delivery_text or 'n/a'})")

    if not found and not delivery_ok:
        return 1
    lines = []
    if found:
        lines.append("Pickup available:\n" + "\n".join(f"• {s}" for s in found))
    if delivery_ok and ALERT_ON_DELIVERY:
        lines.append(f"Online delivery: {delivery_text}")
    if lines:
        notify(f"iPhone Duo {CAPACITY}GB {COLOR.title()} in stock!", "\n\n".join(lines), buy_url)
        return 0
    return 1


def loop(interval_sec):
    realert = float(os.getenv("REALERT_SEC", "60"))
    last_alert = 0.0
    backoff = 0
    real_notify = globals()["notify"]

    def throttled(title, body, url):
        nonlocal last_alert
        if time.time() - last_alert >= realert:
            real_notify(title, body, url)
            last_alert = time.time()

    globals()["notify"] = throttled
    print(f"Checking every {interval_sec:g}s. Ctrl+C to stop.")
    while True:
        try:
            run_once()
            backoff = 0
        except Exception as e:  # noqa: BLE001
            # Apple is probably rate limiting us: slow down for a bit instead of getting blocked
            backoff = min(backoff * 2 or 30, 600)
            print(f"[loop] {e} -> pausing {backoff}s")
            time.sleep(backoff)
        time.sleep(interval_sec)


if __name__ == "__main__":
    sec = os.getenv("INTERVAL_SEC")
    mins = os.getenv("INTERVAL_MIN")
    if sec or mins:
        loop(float(sec) if sec else float(mins) * 60)
    else:
        rc = run_once()
        sys.exit(0 if rc in (0, 1) else rc)
