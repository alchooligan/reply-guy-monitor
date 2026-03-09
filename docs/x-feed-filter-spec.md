# X Feed Filter Rules

For use in the X Monitor cron (hourly scan → Telegram delivery).
Goal: deliver exactly **5 reply-able tweets per hour**, every hour.

---

## Architecture: Cascade Filter

The bot runs tweets through 3 tiers. Tier 1 is the tightest filter. If Tier 1 produces 5+ tweets, send the top 5 and stop. If not, widen to Tier 2. If still short, widen to Tier 3. Always deliver 5.

```
Raw feed (~40-60 tweets)
  │
  ▼
HARD FILTERS (kill noise, always applied)
  │
  ▼
TIER 1 — Prime targets (on-topic + reply-able + signal)
  │  got 5+? → send top 5, done
  ▼
TIER 2 — Solid but broader (adjacent topics, lower signal)
  │  got 5+ combined? → send top 5, done
  ▼
TIER 3 — Anything that survived hard filters (fallback)
  │  send top 5 by engagement, done
```

---

## Hard Filters (Always Applied)

These kill tweets before any topic filtering. Non-negotiable.

### Drop if:

| Rule | Why |
|---|---|
| `text.length < 15` | Nothing to reply to |
| `isRetweet === true` AND no added text | Pure RT, no context, no reply surface |
| Tweet is a reply to someone else (starts with `@`) AND the parent tweet isn't visible | Missing context = bad reply. Exception: if the reply itself is a standalone take (>80 chars, doesn't depend on parent) |
| Author is in `SKIP_AUTHORS` list | Noise accounts (elonmusk, unusual_whales, ahamo_official, etc.) |
| Matches `NOISE_PATTERNS` (giveaway, airdrop, follow me, like & RT, drop your) | Engagement farming spam |
| Tweet is purely an image/video with no text or <15 chars of text | Nothing to reply to with words |
| Tweet is a thread tweet (2/n, 3/n etc.) without the thread starter | Replying to middle of thread looks lost |
| Author follower count < 500 (if available) | Low-reach replies, not worth the slot |
| Duplicate content (same text seen in last 24h from different author) | Copypasta / viral reposts |

### Skip authors list (expand as needed):

```
elonmusk, unusual_whales, ahamo_official,
caboringbot, cb_doge, WatcherGuru, whale_alert,
DailyLoud, PopBase, Reuters, AP
```

Basically: news wires, engagement bait mega-accounts, bot accounts.

---

## Topic Classification

Every tweet that survives hard filters gets classified into one of these buckets. This is the core of the filter.

### Tier 1 Topics — "This is my feed"

These are Cos's lanes. Tweets in these categories are always worth surfacing.

- **DeFi mechanics** — protocols, yields, liquidity, MEV, lending, stablecoins, perps, AMMs, vaults
- **AI x Crypto** — AI agents, agent infrastructure, on-chain AI, compute markets, agent frameworks
- **Market structure** — macro takes, cycle positioning, what's working / what's dying, sector rotation
- **Stablecoins & payments** — issuance, adoption, fintechs, cross-border, USDC/USDT dynamics
- **Protocol strategy & growth** — GTM, tokenomics, community building, launch strategy, growth loops
- **Builder culture** — shipping, vibe coding, dev experience, open source, what it's like to build right now
- **Solana ecosystem** — SOL-specific takes, Solana protocols, Solana vs ETH positioning
- **Prediction markets** — Polymarket, prediction market design, resolution mechanics, yield on predictions
- **Token design & economics** — buybacks, revenue share, governance, value accrual, token utility
- **Onchain data / takes** — specific protocol metrics, TVL moves, volume shifts, wallet analysis

**Keyword signals (non-exhaustive):**
```
defi, stablecoin, usdc, usdt, yield, tvl, liquidity, protocol,
onchain, on-chain, airdrop (only if analytical, not promotional),
solana, sol, ethereum, eth, l1, l2, rollup, bridge,
ai agent, llm, inference, compute, mcp, framework,
polymarket, prediction market, perps, perpetual, amm,
tokenomics, buyback, revenue, governance, dao,
mev, intent, solver, sequencer, restaking,
stablecoin, payments, fintech, remittance,
shipping, building, launched, open source, repo, github
```

### Tier 2 Topics — "I'd engage if the take is good"

Adjacent to Cos's core but not his primary lane. Good for variety and broader reach.

- **Crypto culture & CT commentary** — meta takes about crypto twitter, the industry, conferences
- **Founder / operator life** — startup lessons, hiring, remote work, decision-making, burnout
- **Tech industry (non-crypto)** — AI developments (OpenAI, Anthropic, etc.), dev tools, tech trends
- **Content & personal branding** — growth strategies, audience building, creator economy (crypto-adjacent)
- **Vietnam / SEA crypto scene** — local ecosystem, regional developments
- **Macro / geopolitics** — only when directly tied to markets or crypto (regulation, policy, sanctions)

### Tier 3 Topics — "Fallback, better than nothing"

Only used when Tier 1 + Tier 2 don't fill 5 slots.

- **General tech opinions** — hot takes about products, apps, platforms
- **Lifestyle with a take** — not "here's my coffee" but "here's what living in X taught me about Y"
- **Memes with substance** — CT memes that have an actual market observation underneath
- **Anything from high-follower accounts** (50k+) that isn't spam — reply visibility matters

### Hard block topics — Never surface these regardless of tier:

- **Pure lifestyle** — food pics, travel selfies, gym flexes, outfit checks (unless from a close mutual with a reply-able caption)
- **Promotional threads** — "10 reasons why [token] will 100x", shill threads, launch announcements that are just hype
- **Engagement farming** — "What's your unpopular crypto opinion?", "Name a coin and I'll rate it", polls with no substance
- **Political culture war** — US politics, social issues, identity debates (unless directly about crypto regulation)
- **Sports, entertainment, celebrity gossip**
- **Inspirational / motivational quotes** — "The grind never stops", hustle culture, LinkedIn energy
- **GM/GN posts** — unless they contain actual content beyond the greeting
- **Price predictions without analysis** — "BTC to 200k", "ETH is dead" with no reasoning

---

## Reply-ability Score

After topic filtering, rank surviving tweets by how reply-able they are for Cos specifically. This is what separates "good tweet" from "tweet I should reply to."

### High reply-ability (boost priority):

| Signal | Why it works for Cos |
|---|---|
| Makes a specific claim that can be extended or challenged | Cos's best replies add one layer or push back |
| Asks a question (genuine, not engagement bait) | Cos replies to real questions with specific knowledge |
| References a protocol/project Cos knows | He can add insider context |
| Hot take that's partially right | "agree but..." is Cos's sweet spot |
| From an account with 5k-100k followers | Sweet spot for reply visibility vs. competition |
| <2 replies so far | Early reply = top of thread |
| Posted in last 30 min | Freshness matters for algo |

### Low reply-ability (deprioritize):

| Signal | Why it doesn't work |
|---|---|
| Already has 50+ replies | Cos's reply gets buried |
| Pure announcement (no opinion to engage with) | "We just launched X" — nothing to riff on |
| Thread (3+ tweets) | Reply surface is unclear, most people won't click through |
| Very niche technical detail Cos wouldn't know | Replying looks uninformed |
| From mega-accounts (500k+) | Reply drowns in thousands |
| Vague / abstract philosophy | "Web3 is about ownership" — no specific hook |

---

## Sorting & Selection (Final 5)

Once tweets are classified and scored, select the top 5 using this priority stack:

1. **Tier 1 + High reply-ability + <30 min old** → always #1 priority
2. **Tier 1 + any reply-ability + <60 min old** → fill remaining slots
3. **Tier 2 + High reply-ability + <60 min old** → fill if Tier 1 is thin
4. **Tier 1 from expanded window (1-4h)** → better to surface an older on-topic tweet than a recent off-topic one
5. **Tier 2 + decent engagement (>500 views)** → visibility play
6. **Tier 3 + highest engagement** → last resort, always fill to 5

### Diversity rule:
No more than 2 tweets from the same author in one batch. No more than 3 tweets on the exact same sub-topic (e.g., don't send 4 stablecoin tweets).

---

## Delivery Format

Each tweet in the Telegram message should include:

```
[TIER 1 🎯 / TIER 2 🔵 / TIER 3 ⚪] @author · 23min · 3 replies

Tweet text (truncated to 280 chars if needed)

💬 [5-15 word reply suggestion in Cos's voice — lowercase, no punctuation pressure, riffs on the specific point]

🔗 link
```

### Reply suggestion rules:
- **5-15 words max.** If you can't say it in 15 words, skip the suggestion.
- **Always reference something specific from the tweet.** Never generic.
- **Match Cos's voice:** lowercase, casual, one layer added, no explanations.
- **Sometimes just a reaction is right:** "hell of a drug", "this but unironically", "the real answer nobody wants to hear"
- **Never start with "I think" or "Great point"**
- **Include a suggestion for every tweet.** Don't skip any. If the suggestion is weak, flag it with (weak) so Cos knows to freestyle.

---

## Implementation Notes

### Where topic classification happens:

The hard filters run in the Python script (fast, deterministic). Topic classification and reply-ability scoring happen in the Claude prompt — Claude processes the batch and returns exactly 5 tweets with tier labels, reply suggestions, and ranking.

### Prompt structure for Claude:

```
You are selecting tweets for @0x_cos to reply to.

HARD RULES:
- Select exactly 5 tweets from the batch below.
- Classify each as TIER 1 / TIER 2 / TIER 3 using the topic rules.
- Prioritize Tier 1 > Tier 2 > Tier 3.
- Score reply-ability based on: specific claim, question, early thread, right follower range.
- Write a 5-15 word reply suggestion for each. Lowercase, casual, riff on the specific point.
- Never skip a tweet. Always suggest 5 with replies.
- If the batch has fewer than 5 viable tweets, include the best available and mark weak ones.

TOPIC RULES:
[paste Tier 1/2/3 definitions and block list from above]

REPLY VOICE:
[paste from reply-style.md — ultra short, riffs on specifics, lowercase, one layer, never "I think" or "Great point"]

BATCH:
[tweets JSON]
```

### What stays in the Python script (hard filters):

```python
SKIP_AUTHORS = {
    "elonmusk", "unusual_whales", "ahamo_official",
    "caboringbot", "cb_doge", "watcherguru", "whale_alert",
    "dailyloud", "popbase", "reuters", "ap",
}

NOISE_PATTERNS = [
    re.compile(r'\bgiveaway\b', re.I),
    re.compile(r'\bfollow (?:me|and rt|& rt)\b', re.I),
    re.compile(r'\blike (?:and|&) (?:retweet|rt)\b', re.I),
    re.compile(r'\bdrop (?:your )?(?:wallet|bag|address|eth)\b', re.I),
    re.compile(r'\brt to win\b', re.I),
    re.compile(r'\bwhitelist\b', re.I),
    re.compile(r'\bclick (?:the )?link in (?:my )?bio\b', re.I),
    re.compile(r'\bunpopular opinion.*\?', re.I),
    re.compile(r'\bname a coin\b|\bdrop your bags?\b', re.I),
    re.compile(r'^gm\W{0,5}$|^gn\W{0,5}$', re.I),
]
```

### What Claude handles (topic + ranking + suggestions):

Everything from topic classification onward. The script feeds Claude a clean batch (post-hard-filter), and Claude returns exactly 5 tweets with tier labels, reply suggestions.

---

## Tuning Over Time

- Track which tier Cos actually replies to → if he's consistently ignoring Tier 2/3, tighten the topic filter
- Track reply suggestion usage → if he's always rewriting, the voice calibration is off
- Add accounts to SKIP_AUTHORS as needed
- Expand/contract Tier 1 keywords based on what Cos is actually posting about (feed this from voice trainer updates)
- If certain times of day consistently produce thin feeds, consider adjusting the scan window for those hours
