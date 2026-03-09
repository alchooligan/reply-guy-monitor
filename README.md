# Reply Guy Monitor

Scrapes your X Following feed every hour. Filters the noise. Sends 5 reply-able tweets to your Telegram — each one with a draft reply written in your voice.

Built for people who want to stay consistently active on CT without doomscrolling all day.

---

## What it does

Every hour (during your active window):

1. Loads your X Following feed using a stealthy headless browser
2. Hard filters — drops pure RTs, spam, orphan replies, gm posts, thread mid-tweets, noise accounts
3. Sends the clean batch to Claude, which picks the 5 best tweets by topic tier and reply-ability
4. Claude writes a short reply suggestion for each one in your voice
5. One Telegram message lands in your phone

Open Telegram → review → post. Done in under a minute.

```
🎯 @satoshi · 12m

Bitcoin's Lightning Network has more nodes than 80% of traditional payment networks. 
The infrastructure argument is dead.

lol lightning is like 5% of bitcoin transactions tho

↗ view tweet
```

---

## How it filters

Tweets pass through two layers:

**Hard filters (Python, always applied)**
- Drops pure RTs, spam, engagement bait, gm/gn posts, mid-thread tweets
- Drops accounts in your skip list (bots, mega-accounts, news wires)
- Drops replies to other people that don't stand alone

**Soft filters (Claude, topic-aware)**
- Tier 1 🎯 — your core topics (always surface)
- Tier 2 🔵 — adjacent topics (surface if the take is good)
- Tier 3 ⚪ — fallback (last resort to fill 5 slots)

Claude always delivers exactly 5. Topic tiers are fully customizable.

Full spec: `docs/x-feed-filter-spec.md`

---

## Requirements

- Python 3.10+
- A Telegram bot (free, 2 min setup)
- X account with auth cookies
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and logged in — this is what writes the reply suggestions. Works with Claude Max subscription, no separate API key needed.

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/yourusername/reply-guy-monitor
cd reply-guy-monitor
pip install "scrapling[fetchers]" httpx
scrapling install
```

### 2. Create your Telegram bot

1. Open Telegram, message **@BotFather**
2. Send `/newbot` → follow the prompts → copy the bot token
3. Start a chat with your new bot
4. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in your browser
5. Send any message to your bot, refresh — copy your `id` from the `chat` object

### 3. Get your X auth cookies

1. Log into x.com in Chrome/Firefox
2. Open DevTools (`F12`) → Application → Cookies → `https://x.com`
3. Copy `auth_token` and `ct0`

Paste them into `.secrets/x_auth.json`:

```json
{
  "auth_token": "paste your auth_token here",
  "ct0": "paste your ct0 here"
}
```

> These cookies expire occasionally (weeks to months). The bot will warn you on Telegram when it detects a stale token.

### 4. Add your Telegram credentials

Open `scripts/x_feed_monitor.py` and `scripts/tg_listener.py`. Replace:

```python
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"
```

### 5. Set up your voice

Open `prompts/voice-setup.md` and fill it in. Takes 15-20 minutes. This directly determines how good the reply suggestions sound.

The output becomes `prompts/reply-style.md` — the voice guide Claude reads every run.

### 6. Test it

```bash
python scripts/x_feed_monitor.py
```

Check Telegram. If 5 tweets showed up with suggestions, you're done.

---

## Automate it (Windows Task Scheduler)

Two XML task files are included:
- `task.xml` — runs the monitor hourly during your active hours
- `listener_task.xml` — starts the Telegram listener at login

Before importing, open both XML files and update:
- The Python executable path
- The script paths
- The working directory

Then register:

```powershell
schtasks /create /tn "XFeedMonitor" /xml task.xml
schtasks /create /tn "XFeedListener" /xml listener_task.xml
```

---

## Telegram commands

Once the listener is running, control everything from your phone:

| Command | What it does |
|---|---|
| `/run` | Trigger a fresh fetch right now |
| `/clear` | Reset the seen list (re-surface recent tweets) |
| `/status` | Show last run time and tweet count |

---

## Customizing filters

In `scripts/x_feed_monitor.py`:

```python
SKIP_AUTHORS = {"elonmusk", "whale_alert", ...}  # always ignore these
NOISE_PATTERNS = [...]                             # regex list for spam
LOOKBACK_HOURS = 4.0                               # how far back to look
TARGET_TWEETS = 5                                  # how many to deliver per run
```

To change your topic tiers (what counts as Tier 1 / 2 / 3 for you), edit the `_build_selection_prompt()` function in the monitor script. The full spec is in `docs/x-feed-filter-spec.md`.

---

## Running costs

Reply suggestions run via Claude Code CLI (`claude -p`), which uses your Claude Max subscription. No separate API key needed. If you don't have Claude Max, you can swap in the Anthropic API — see `_call_claude()` in the monitor script.

The hourly scraping is local — no cloud, no external costs.

---

## Files

```
scripts/
  x_feed_monitor.py   — main hourly scraper + filter + delivery
  tg_listener.py      — Telegram command listener
  x_style_learner.py  — weekly script to update your voice profile (optional)

prompts/
  voice-setup.md      — fill this in first
  reply-style.md      — your compiled voice guide (output of voice-setup)

docs/
  x-feed-filter-spec.md  — full filter architecture spec

.secrets/
  x_auth.json         — your X cookies (gitignored)

data/                 — runtime data, gitignored
  x-feed-seen.json    — dedup tracker
  x-monitor-log.jsonl — run history
```

---

## License

MIT.
