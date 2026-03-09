#!/usr/bin/env python3
"""
X Feed Monitor — hourly tweet scraper with cascade filtering and reply suggestions.

Architecture:
  1. Scrape X Following feed (~40-60 tweets)
  2. Apply hard filters (noise, spam, orphan replies, thread fragments, skip-list authors)
  3. Claude selects exactly 5 tweets by tier priority + writes 5-15 word reply suggestions
  4. Deliver to Telegram with tier label, age, reply count, and suggestion

See docs/x-feed-filter-spec.md for full filter rules.

Setup:
  pip install "scrapling[fetchers]" httpx
  scrapling install
  Fill in .secrets/x_auth.json with auth_token and ct0 cookies from x.com
"""

import html
import json
import logging
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from scrapling.fetchers import StealthyFetcher

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
SECRETS = ROOT / ".secrets"
DATA = ROOT / "data"
PROMPTS = ROOT / "prompts"

SEEN_FILE = DATA / "x-feed-seen.json"
LOG_FILE = DATA / "x-monitor-log.jsonl"
PATTERNS_FILE = DATA / "reply-patterns.json"
STYLE_GUIDE_FILE = PROMPTS / "reply-style.md"
AUTH_FILE = SECRETS / "x_auth.json"
FALLBACK_FILE = DATA / "telegram-fallback.txt"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"   # from @BotFather
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"  # your personal chat ID
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

TARGET_TWEETS = 5       # always deliver exactly this many
MAX_INPUT_TWEETS = 30   # cap fed to Claude (keeps prompt manageable)
LOOKBACK_HOURS = 4.0    # hard age cutoff — skip tweets older than this

# Authors to always skip regardless of content
SKIP_AUTHORS = {
    "elonmusk", "unusual_whales", "ahamo_official",
    "caboringbot", "cb_doge", "watcherguru", "whale_alert",
    "dailyloud", "popbase", "reuters", "ap",
}

# Regex patterns — any match → drop the tweet
NOISE_PATTERNS = [
    re.compile(r'\bgiveaway\b', re.I),
    re.compile(r'\bfollow (?:me|and rt|& rt)\b', re.I),
    re.compile(r'\blike (?:and|&) (?:retweet|rt)\b', re.I),
    re.compile(r'\bdrop (?:your )?(?:wallet|bag|address|eth)\b', re.I),
    re.compile(r'\brt to win\b', re.I),
    re.compile(r'\bwhitelist\b', re.I),
    re.compile(r'\bsubscribe to\b', re.I),
    re.compile(r'\bclick (?:the )?link in (?:my )?bio\b', re.I),
    re.compile(r'\bunpopular opinion.*\?', re.I),
    re.compile(r'\bname a coin\b|\bdrop your bags?\b', re.I),
    re.compile(r'^gm\W{0,5}$|^gn\W{0,5}$', re.I),  # pure gm/gn with no content
]

# Thread position markers ("2/5", "3/", "(2/4)" etc.) — mid-thread = missing context
THREAD_PATTERN = re.compile(r'\b\d+/\d+\b|\(\d+/\d+\)|\b\d+/\s*$')

# Telegram tier labels
TIER_EMOJI = {1: "🎯", 2: "🔵", 3: "⚪"}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------
def load_auth() -> dict:
    with open(AUTH_FILE) as f:
        return json.load(f)


def find_claude_bin() -> str | None:
    """Find the `claude` CLI binary, checking PATH and common install locations."""
    found = shutil.which("claude")
    if found:
        return found
    candidates = [
        Path.home() / "AppData/Roaming/npm/claude.cmd",
        Path.home() / "AppData/Roaming/npm/claude",
        Path.home() / ".local/bin/claude",
        Path("/usr/local/bin/claude"),
        Path("/opt/homebrew/bin/claude"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    log.warning("claude binary not found")
    return None


# ---------------------------------------------------------------------------
# Seen list
# ---------------------------------------------------------------------------
def load_seen() -> set:
    if SEEN_FILE.exists():
        data = json.loads(SEEN_FILE.read_text())
        return set(data.get("ids", []))
    return set()


def save_seen(seen: set):
    ids = list(seen)[-5000:]
    SEEN_FILE.write_text(json.dumps({"ids": ids}, indent=2))


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------
def _click_following_tab(page) -> None:
    """Playwright page_action (sync): click Following tab, then scroll to load ~40-60 tweets."""
    try:
        page.wait_for_selector('[role="tab"]', timeout=8000)
    except Exception:
        pass
    page.evaluate("""
        () => {
            const tabs = document.querySelectorAll('[role="tab"]');
            for (const tab of tabs) {
                if (tab.textContent.trim() === 'Following') {
                    tab.click();
                    return;
                }
            }
        }
    """)
    try:
        page.wait_for_selector('article[data-testid="tweet"]', timeout=8000)
    except Exception:
        pass

    # Scroll down to trigger lazy-loading — X only renders ~6-8 tweets on first paint
    for _ in range(4):
        page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
        try:
            page.wait_for_timeout(1500)
        except Exception:
            import time
            time.sleep(1.5)


def scrape_following_feed(auth: dict) -> list[dict]:
    """Load X Following tab and return raw tweet dicts."""
    cookies = [
        {"name": "auth_token", "value": auth["auth_token"], "domain": ".x.com", "path": "/"},
        {"name": "ct0", "value": auth["ct0"], "domain": ".x.com", "path": "/"},
        {"name": "lang", "value": "en", "domain": ".x.com", "path": "/"},
    ]

    log.info("Fetching X Following feed via StealthyFetcher...")
    try:
        response = StealthyFetcher.fetch(
            "https://x.com/home",
            cookies=cookies,
            page_action=_click_following_tab,
            wait_selector='article[data-testid="tweet"]',
            network_idle=False,
        )
    except Exception as e:
        log.error(f"Scraping failed: {e}")
        return []

    return parse_tweets(response)


def _parse_count(label: str) -> int:
    """Parse integer from aria-label like '3 replies' or '1.2K views'."""
    m = re.search(r'([\d.]+)\s*([KkMm]?)', label)
    if not m:
        return 0
    num = float(m.group(1))
    suffix = m.group(2).upper()
    if suffix == "K":
        return int(num * 1_000)
    elif suffix == "M":
        return int(num * 1_000_000)
    return int(num)


def parse_tweets(response) -> list[dict]:
    tweets = []
    try:
        articles = response.css('article[data-testid="tweet"]')
    except Exception as e:
        log.error(f"Failed to find tweet articles: {e}")
        return []

    for article in articles:
        try:
            tweet = extract_tweet(article)
            if tweet:
                tweets.append(tweet)
        except Exception as e:
            log.debug(f"Skipped article: {e}")

    log.info(f"Parsed {len(tweets)} raw tweets")
    return tweets


def extract_tweet(article) -> dict | None:
    # Handle: find /username link inside user-name container
    handle = None
    try:
        for el in article.css('[data-testid="User-Name"] a'):
            href = el.attrib.get("href", "")
            if href.startswith("/") and href.count("/") == 1:
                handle = href.strip("/")
                break
    except Exception:
        pass

    if not handle:
        return None

    # Tweet text
    text = ""
    try:
        text = " ".join(
            el.get_all_text() for el in article.css('[data-testid="tweetText"]')
        ).strip()
    except Exception:
        pass

    if not text:
        return None

    # Timestamp + tweet URL
    tweet_url = None
    ts: datetime | None = None
    try:
        time_els = article.css("time")
        if time_els:
            dt_str = time_els[0].attrib.get("datetime", "")
            if dt_str:
                ts = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            parent = time_els[0].parent
            if parent and parent.tag == "a":
                href = parent.attrib.get("href", "")
                if "/status/" in href:
                    tweet_url = f"https://x.com{href}"
    except Exception:
        pass

    # Tweet ID
    tweet_id = None
    if tweet_url and "/status/" in tweet_url:
        tweet_id = tweet_url.split("/status/")[-1].split("?")[0].split("/")[0]

    if not tweet_id:
        return None

    if not tweet_url:
        tweet_url = f"https://x.com/{handle}/status/{tweet_id}"

    # is_retweet: "Reposted" in social context header
    is_retweet = False
    try:
        ctx = article.css('[data-testid="socialContext"]')
        if ctx and "repost" in ctx[0].get_all_text().lower():
            is_retweet = True
    except Exception:
        pass

    # is_reply: tweet text starts with @username (replying to someone)
    is_reply = bool(re.match(r'^@\w+', text))

    # reply_count from the reply button aria-label
    reply_count = 0
    try:
        btn = article.css('[data-testid="reply"]')
        if btn:
            reply_count = _parse_count(btn[0].attrib.get("aria-label", ""))
    except Exception:
        pass

    return {
        "id": tweet_id,
        "handle": handle,
        "text": text,
        "url": tweet_url,
        "ts": ts,
        "is_retweet": is_retweet,
        "is_reply": is_reply,
        "reply_count": reply_count,
    }


# ---------------------------------------------------------------------------
# Hard Filters (always applied before Claude sees the batch)
# ---------------------------------------------------------------------------
def apply_hard_filters(tweets: list, seen: set) -> list:
    """Non-negotiable pre-filters. See docs/x-feed-filter-spec.md."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    result = []

    for t in tweets:
        # Already delivered
        if t["id"] in seen:
            continue

        # Too old
        if t.get("ts") and t["ts"] < cutoff:
            continue

        # Skip-list authors
        if t["handle"].lower() in SKIP_AUTHORS:
            continue

        # Too short to reply to
        if len(t["text"].strip()) < 15:
            continue

        # Pure retweet (no original content added)
        if t.get("is_retweet") and len(t["text"].strip()) < 30:
            continue

        # Reply without enough standalone context (short orphan reply)
        if t.get("is_reply") and len(t["text"]) < 80:
            continue

        # Mid-thread tweet (missing context)
        if THREAD_PATTERN.search(t["text"]):
            continue

        # Noise/spam patterns
        if any(p.search(t["text"]) for p in NOISE_PATTERNS):
            continue

        result.append(t)

    return result


def is_mostly_non_english(tweets: list) -> bool:
    """Heuristic for expired auth: mostly non-ASCII = Japanese ad feed pattern."""
    if not tweets:
        return False
    non_eng = sum(
        1 for t in tweets
        if sum(1 for c in t["text"] if ord(c) < 128 and c.isalpha()) < 5
    )
    return non_eng / len(tweets) > 0.6


# ---------------------------------------------------------------------------
# Claude: select 5 + classify + suggest
# ---------------------------------------------------------------------------
def _extract_json_array(text: str) -> str | None:
    """Extract the first complete JSON array from text using bracket matching.
    Handles nested structures and quoted strings safely."""
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i, c in enumerate(text[start:], start):
        if escape:
            escape = False
            continue
        if c == "\\" and in_string:
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def get_selected_with_suggestions(tweets: list) -> list[dict]:
    """Call Claude to select TARGET_TWEETS tweets with tier labels and reply suggestions.
    Falls back to top-N-by-recency (no suggestions) if Claude is unavailable."""
    if not tweets:
        return []

    if not find_claude_bin():
        log.warning("claude CLI not found — fallback selection")
        return _fallback_selection(tweets)

    if not STYLE_GUIDE_FILE.exists():
        log.warning("reply-style.md missing — fallback selection")
        return _fallback_selection(tweets)

    style_guide = STYLE_GUIDE_FILE.read_text()

    patterns = {}
    if PATTERNS_FILE.exists():
        try:
            patterns = json.loads(PATTERNS_FILE.read_text())
        except Exception:
            pass

    env = {k: v for k, v in __import__("os").environ.items() if k != "CLAUDECODE"}
    batch = tweets[:MAX_INPUT_TWEETS]
    prompt = _build_selection_prompt(batch, style_guide, patterns)

    raw = _call_claude(prompt, env, timeout=120)
    if raw is None:
        log.warning("Claude call failed — fallback selection")
        return _fallback_selection(tweets)

    try:
        # Strip markdown code fence if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])

        # Extract the outermost JSON array — Claude sometimes adds explanation text
        raw = _extract_json_array(raw) or raw

        selected_data: list = json.loads(raw)
        result = []
        selected_indices = set()

        for item in selected_data[:TARGET_TWEETS]:
            idx = item.get("index")
            if idx is None or not isinstance(idx, int) or idx >= len(batch):
                continue
            selected_indices.add(idx)
            result.append({
                "tweet": batch[idx],
                "tier": int(item.get("tier", 3)),
                "suggestion": str(item.get("suggestion", "")).strip(),
            })

        # Pad with fallback tweets if Claude returned fewer than TARGET_TWEETS
        if len(result) < TARGET_TWEETS:
            remaining = [t for i, t in enumerate(batch) if i not in selected_indices]
            for t in sorted(
                remaining,
                key=lambda x: x.get("ts") or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            ):
                if len(result) >= TARGET_TWEETS:
                    break
                result.append({"tweet": t, "tier": 3, "suggestion": ""})

        return result if result else _fallback_selection(tweets)

    except Exception as e:
        log.warning(f"Claude selection parse failed: {e} — fallback")
        return _fallback_selection(tweets)


def _fallback_selection(tweets: list) -> list[dict]:
    """Top-N by recency, no tier or suggestion."""
    sorted_tweets = sorted(
        tweets,
        key=lambda t: t.get("ts") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return [{"tweet": t, "tier": 3, "suggestion": ""} for t in sorted_tweets[:TARGET_TWEETS]]


def _build_selection_prompt(tweets: list, style_guide: str, patterns: dict) -> str:
    now = datetime.now(timezone.utc)

    patterns_block = ""
    if patterns and patterns.get("sample_size", 0) > 0:
        patterns_block = f"\n\n## Learned reply patterns\n{json.dumps(patterns, indent=2)}"

    tweets_json = json.dumps(
        [
            {
                "index": i,
                "handle": f"@{t['handle']}",
                "text": t["text"],
                "age_min": int((now - t["ts"]).total_seconds() / 60) if t.get("ts") else None,
                "reply_count": t.get("reply_count", 0),
            }
            for i, t in enumerate(tweets)
        ],
        indent=2,
    )

    return f"""You are selecting tweets for @0x_cos to reply to. Pick exactly {TARGET_TWEETS} from the batch below.

## Topic Tiers

TIER 1 — Core lanes (always surface):
DeFi mechanics, AI x Crypto, market structure, stablecoins/payments, protocol strategy/growth, builder culture, Solana ecosystem, prediction markets, token economics/design, onchain data.
Keywords: defi, stablecoin, usdc, usdt, yield, tvl, liquidity, protocol, onchain, solana, sol, ethereum, eth, l2, rollup, ai agent, llm, compute, mcp, polymarket, tokenomics, buyback, mev, restaking, perps, amm, bridge, dao, governance, revenue

TIER 2 — Surface if the take is good:
Crypto culture/CT meta, founder/operator life, tech industry (non-crypto AI, dev tools), content/personal branding, macro tied to crypto/markets

TIER 3 — Fallback only:
General tech opinions, lifestyle with a take, memes with substance, high-engagement posts (50k+ follower accounts)

NEVER surface:
- Pure lifestyle (food, travel, gym flex)
- Shill/promotional threads ("10 reasons why X will 100x")
- Engagement farming ("what's your unpopular opinion?", polls, "name a coin")
- Political culture war unrelated to crypto regulation
- Sports, entertainment, celebrity
- Motivational/hustle quotes
- Pure price predictions with no reasoning

## Selection Priority
1. Tier 1 + <30 min old + specific claim or genuine question
2. Tier 1 + any age
3. Tier 2 + high reply-ability + <60 min old
4. Tier 1 from expanded window (up to 4h)
5. Tier 2 + decent reply count
6. Tier 3 by highest reply count (last resort)

## Diversity Rule
Max 2 tweets from the same author. Max 3 tweets on the exact same sub-topic.

## Reply-ability Signals
Boost: specific claim to extend/challenge, genuine question, protocol Cos knows, hot take that's partially right, <2 replies so far, posted <30 min ago
Deprioritize: 50+ replies (buried), pure announcement, mega-account (500k+ followers), vague abstract philosophy

## Reply Style
{style_guide}{patterns_block}

## Reply Suggestion Rules
- 5-15 words max
- Reference something specific from the tweet — never generic
- Lowercase, casual, one layer added or pushed back
- Never start with "I think" or "Great point"
- Include a suggestion for EVERY selected tweet — don't skip any
- If suggestion is weak, add " (weak)" so Cos knows to freestyle

## Output Format
Return ONLY valid JSON — an array of exactly {TARGET_TWEETS} objects, no other text:
[
  {{"index": 0, "tier": 1, "suggestion": "5-15 word reply in cos voice"}},
  {{"index": 3, "tier": 2, "suggestion": "another reply"}},
  ...
]

## Tweet Batch
{tweets_json}"""


# ---------------------------------------------------------------------------
# Claude subprocess
# ---------------------------------------------------------------------------
def _call_claude(prompt: str, env: dict, timeout: int = 120) -> str | None:
    """Call claude CLI with prompt via stdin pipeline. Returns response text or None.

    On Windows: writes prompt to temp file, pipes via PowerShell.
      DO NOT pass prompt as CLI arg ($var gets word-split on whitespace).
      DO NOT use Python input= on a .cmd file (stdin doesn't reach the claude binary).
    On Unix: passes via stdin directly.
    """
    claude_bin = find_claude_bin()
    if not claude_bin:
        return None

    try:
        if sys.platform == "win32":
            import tempfile
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write(prompt)
                tmpfile = f.name
            try:
                npm_bin = str(Path.home() / "AppData" / "Roaming" / "npm")
                ps_cmd = (
                    f"$env:PATH = '{npm_bin};' + $env:PATH; "
                    f"$env:CLAUDECODE = $null; "
                    f"Get-Content '{tmpfile}' -Raw | claude -p --model claude-sonnet-4-6"
                )
                result = subprocess.run(
                    ["powershell.exe", "-NonInteractive", "-NoProfile", "-Command", ps_cmd],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                )
            finally:
                Path(tmpfile).unlink(missing_ok=True)
        else:
            result = subprocess.run(
                [claude_bin, "-p", "--model", "claude-sonnet-4-6"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )

        if result.returncode != 0:
            log.warning(f"claude error: {result.stderr.strip()[:300]}")
            return None

        return result.stdout.strip()

    except subprocess.TimeoutExpired:
        log.warning(f"claude timed out after {timeout}s — skipping")
        return None
    except Exception as e:
        log.warning(f"claude call failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
def format_message(selected: list[dict]) -> str:
    parts = []
    now = datetime.now(timezone.utc)

    for item in selected:
        tweet = item["tweet"]
        tier = item.get("tier", 3)
        suggestion = item.get("suggestion", "")

        # Relative age
        ts_label = ""
        if tweet.get("ts"):
            delta = now - tweet["ts"]
            mins = int(delta.total_seconds() / 60)
            ts_label = f"{mins}m" if mins < 60 else f"{mins // 60}h"

        tier_label = TIER_EMOJI.get(tier, "⚪")
        ts_part = f" · {ts_label}" if ts_label else ""
        rc = tweet.get("reply_count", 0)
        rc_part = f" · {rc}↩" if rc else ""

        header = f"{tier_label} <b>@{tweet['handle']}</b>{ts_part}{rc_part}"
        body = html.escape(tweet["text"])
        link_line = f'<a href="{tweet["url"]}">↗ view tweet</a>'

        block = f"{header}\n\n{body}"

        if suggestion:
            block += f"\n\n<code>{html.escape(suggestion)}</code>"

        block += f"\n\n{link_line}"
        parts.append(block)

    return "\n\n---\n\n".join(parts)


def send_telegram(text: str) -> bool:
    try:
        r = httpx.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=30,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        _fallback_log(text)
        return False


def _fallback_log(message: str):
    """Save unsent message locally so nothing is lost."""
    with open(FALLBACK_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n\n=== {datetime.now().isoformat()} ===\n{message}\n")
    log.info(f"Message saved to {FALLBACK_FILE}")


# ---------------------------------------------------------------------------
# Run log
# ---------------------------------------------------------------------------
def write_log(entry: dict):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    start = datetime.now(timezone.utc)
    log.info(f"Starting at {start.isoformat()}")

    try:
        auth = load_auth()
    except Exception as e:
        log.error(f"Failed to load auth: {e}")
        sys.exit(1)

    seen = load_seen()
    raw_tweets = scrape_following_feed(auth)

    if not raw_tweets:
        log.warning("No tweets scraped")
        write_log({"ts": start.isoformat(), "status": "no_tweets", "count": 0})
        return

    # Auth expiry check: non-English feed = stale token
    if is_mostly_non_english(raw_tweets):
        send_telegram(
            "⚠️ <b>X auth token likely expired</b> — seeing mostly non-English content. Refresh it."
        )
        write_log({"ts": start.isoformat(), "status": "auth_warning"})
        return

    hard_filtered = apply_hard_filters(raw_tweets, seen)
    log.info(f"{len(raw_tweets)} raw -> {len(hard_filtered)} after hard filters")

    if not hard_filtered:
        log.info("Nothing survived hard filters")
        write_log({"ts": start.isoformat(), "status": "filtered_empty"})
        return

    # Claude selects TARGET_TWEETS + classifies + suggests
    selected = get_selected_with_suggestions(hard_filtered)

    if not selected:
        log.warning("No tweets selected")
        write_log({"ts": start.isoformat(), "status": "no_selection"})
        return

    tiers = [s["tier"] for s in selected]
    log.info(f"Delivering {len(selected)} tweets, tiers: {tiers}")

    message = format_message(selected)
    sent = send_telegram(message)

    save_seen(seen | {s["tweet"]["id"] for s in selected})

    write_log({
        "ts": start.isoformat(),
        "status": "sent" if sent else "fallback",
        "count": len(selected),
        "suggestions": sum(1 for s in selected if s.get("suggestion")),
        "tiers": tiers,
    })
    log.info("Done.")


if __name__ == "__main__":
    main()
