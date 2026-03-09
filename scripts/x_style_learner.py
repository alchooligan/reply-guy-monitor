#!/usr/bin/env python3
"""
X Style Learner — scrapes my replies and generates learned patterns via Claude Opus.

Run manually, roughly once a week:
  python scripts/x_style_learner.py

Output: data/reply-patterns.json (picked up by x_feed_monitor.py on next run)

The hand-maintained prompts/reply-style.md is NEVER touched by this script.
"""

import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from scrapling.fetchers import StealthyFetcher

ROOT = Path(__file__).parent.parent
SECRETS = ROOT / ".secrets"
DATA = ROOT / "data"

PATTERNS_FILE = DATA / "reply-patterns.json"
AUTH_FILE = SECRETS / "x_auth.json"

MY_HANDLE = "0x_cos"
MAX_REPLIES = 50

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
    found = shutil.which("claude")
    if found:
        return found
    candidates = [
        Path.home() / ".local/bin/claude",
        Path("/usr/local/bin/claude"),
        Path("/opt/homebrew/bin/claude"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------
def _wait_for_tweets(page) -> None:
    try:
        page.wait_for_selector('article[data-testid="tweet"]', timeout=10000)
    except Exception:
        pass


def scrape_my_replies(auth: dict) -> list[dict]:
    """Scrape with_replies tab for @0x_cos and extract reply pairs."""
    cookies = [
        {"name": "auth_token", "value": auth["auth_token"], "domain": ".x.com", "path": "/"},
        {"name": "ct0", "value": auth["ct0"], "domain": ".x.com", "path": "/"},
        {"name": "lang", "value": "en", "domain": ".x.com", "path": "/"},
    ]

    url = f"https://x.com/{MY_HANDLE}/with_replies"
    log.info(f"Scraping {url}")

    try:
        response = StealthyFetcher.fetch(
            url,
            cookies=cookies,
            page_action=_wait_for_tweets,
            wait_selector='article[data-testid="tweet"]',
            network_idle=False,
        )
    except Exception as e:
        log.error(f"Scraping failed: {e}")
        return []

    return parse_reply_pairs(response)


def parse_reply_pairs(response) -> list[dict]:
    """Extract pairs of (original tweet, my reply) from the with_replies page."""
    try:
        articles = response.css('article[data-testid="tweet"]')
    except Exception as e:
        log.error(f"Parse error: {e}")
        return []

    all_tweets = []
    for article in articles:
        try:
            handle, text = _extract_handle_and_text(article)
            if handle and text:
                all_tweets.append({"handle": handle.lower(), "text": text})
        except Exception:
            continue

    my_handle = MY_HANDLE.lower().lstrip("@")
    pairs = []
    for i, tweet in enumerate(all_tweets):
        if tweet["handle"] == my_handle and i > 0:
            pairs.append({
                "original_author": all_tweets[i - 1]["handle"],
                "original": all_tweets[i - 1]["text"],
                "my_reply": tweet["text"],
            })
        if len(pairs) >= MAX_REPLIES:
            break

    log.info(f"Found {len(pairs)} reply pairs")
    return pairs


def _extract_handle_and_text(article) -> tuple[str | None, str | None]:
    handle = None
    handle_links = article.css('[data-testid="User-Name"] a')
    for el in handle_links:
        href = el.attrib.get("href", "")
        if href.startswith("/") and href.count("/") == 1:
            handle = href.strip("/")
            break

    text = ""
    text_els = article.css('[data-testid="tweetText"]')
    text = " ".join(el.get_all_text() for el in text_els).strip()

    return handle, text or None


# ---------------------------------------------------------------------------
# Pattern analysis via claude CLI
# ---------------------------------------------------------------------------
def analyze_patterns(pairs: list[dict]) -> dict:
    """Send reply pairs to Claude Opus via `claude -p` for pattern analysis."""
    claude_bin = find_claude_bin()
    if not claude_bin:
        log.error("claude CLI not found — install Claude Code and run `claude` once to log in")
        sys.exit(1)

    pairs_text = "\n\n".join(
        f"Original (@{p['original_author']}): {p['original']}\nMy reply: {p['my_reply']}"
        for p in pairs
    )

    prompt = f"""Analyze these {len(pairs)} real replies I've made on X (Twitter) and extract my writing patterns.

{pairs_text}

Output a JSON object with these fields:
- tone: array of adjectives describing my tone
- avg_length: "short", "medium", or "long"
- sentence_style: how I structure sentences
- vocabulary: array of words/phrases I use often
- engagement_triggers: what kinds of tweets I reply to
- avoidance_patterns: what I tend not to engage with
- recurring_structures: array of reply templates/patterns I use
- humor_style: how I use humor if at all
- formatting_notes: punctuation habits, caps, emoji usage, etc.

Respond with only the JSON object. No markdown, no explanation."""

    log.info("Sending to Claude Opus via claude CLI...")
    result = subprocess.run(
        [claude_bin, "-p", "--model", "claude-opus-4-6", prompt],
        capture_output=True,
        text=True,
        timeout=180,
    )

    if result.returncode != 0:
        raise RuntimeError(f"claude CLI error: {result.stderr.strip()}")

    raw = result.stdout.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    return json.loads(raw)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    log.info("X Style Learner starting")

    try:
        auth = load_auth()
    except Exception as e:
        log.error(f"Failed to load auth: {e}")
        sys.exit(1)

    pairs = scrape_my_replies(auth)
    if not pairs:
        log.error("No reply pairs found — check auth token and try again")
        sys.exit(1)

    patterns = analyze_patterns(pairs)
    patterns["generated_at"] = datetime.now(timezone.utc).isoformat()
    patterns["sample_size"] = len(pairs)

    DATA.mkdir(exist_ok=True)
    PATTERNS_FILE.write_text(json.dumps(patterns, indent=2))
    log.info(f"Patterns written to {PATTERNS_FILE}")
    log.info("Done. x_feed_monitor.py will pick this up on the next run.")


if __name__ == "__main__":
    main()
