# iPhone Duo 512GB Star White watcher (Apple UAE)

Checks apple.com/ae every few minutes for store pickup (Dubai Mall, Mall of the Emirates, Yas Mall, Al Maryah Island) and online delivery, then pings your phone.

## 1. Get alerts on your phone (2 minutes)

Easiest: **ntfy**
1. Install the free **ntfy** app (iOS / Android).
2. Tap **+**, subscribe to a topic name only you know, e.g. `sagar-duo-7k3x9q`.
3. That name is your `NTFY_TOPIC`.

Optional: **Telegram** — create a bot with @BotFather (gives `TELEGRAM_BOT_TOKEN`), message it once, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` to read your `chat.id` (`TELEGRAM_CHAT_ID`).

## 2a. Run it free on GitHub (works while your laptop is off)

1. Create a new **public** GitHub repo (public = unlimited free Actions minutes) and upload `watch.py` plus the `.github/workflows/watch.yml` folder.
2. Repo → Settings → Secrets and variables → Actions → **New repository secret**: `NTFY_TOPIC` (and the Telegram ones if you use them). Secrets stay hidden even in a public repo.
3. Actions tab → enable workflows → open **iPhone Duo watch** → **Run workflow** to test. Check the log line, it shows the part number and current status.

It then runs every 10 minutes by itself.

## 2b. Every 5 seconds: run it on your Mac

GitHub can only check every 5 minutes. For every 5 seconds, open Terminal in the unzipped folder and run:

```bash
export NTFY_TOPIC=sagar-duo-7k3x9q
INTERVAL_SEC=5 caffeinate -i python3 watch.py
```
Keep the Terminal window open and the Mac plugged in. `caffeinate` stops it sleeping. Ctrl+C stops the bot.

* While stock shows, you get at most one alert a minute (change with `REALERT_SEC`).
* If Apple starts refusing requests, the bot pauses on its own (30s, then longer) and carries on afterwards. If you see that a lot, use `INTERVAL_SEC=15`.

## If it says it can't find the part number

Open the 512GB Star White config on apple.com/ae, view page source, search `partNumber`, and copy the code that ends in `/A` (likely `MK2F4AH/A`). Then:
* GitHub: Settings → Secrets and variables → Actions → **Variables** → `PART_NUMBER`
* Mac: `export PART_NUMBER=MK2F4AH/A`

## Tweaks

* Only care about pickup? set `ALERT_ON_DELIVERY=0`
* Other model: `CAPACITY=1024`/`COLOR="night sky"` or just set `PART_NUMBER`
* While stock is showing you'll get a ping each run, which is deliberate so you don't miss it. Turn off the workflow once you've ordered.
