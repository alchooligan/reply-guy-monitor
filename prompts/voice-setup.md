# Voice Setup

The reply suggestions are only as good as your voice guide. Spend 20 minutes here and the output actually sounds like you. Rush it and you'll get generic slop.

Fill this in, then build your `prompts/reply-style.md` from it.

---

## 1. what's your actual lane

Not your Twitter bio. What do you *genuinely* know well enough to add something when you reply?

Be specific. "crypto" is not a lane. "DeFi protocol design and yield strategies" is. "AI infrastructure" is. "B2B SaaS growth" is.

> [your answer]

---

## 2. what kind of tweet makes you actually want to reply

Think about the last 5 times you replied on X without thinking about it. What type of tweet was it?

Was it:
- a take you disagreed with?
- a question in your space where you knew the answer?
- a take that was almost right but missing one layer?
- someone sharing a data point you could extend?
- something that annoyed you just enough to say something?

> [describe what pulls a reply out of you — be specific]

---

## 3. what do you scroll past without stopping

The content that makes you tap past instantly. What is it?

> [your answer]

---

## 4. your 15 best replies

This is the most important section. Everything else is context. This is the data.

Find 15 replies you've posted where you felt like it sounded exactly like you. Not the ones that got the most likes — the ones that felt right.

For each one, paste the original tweet and your reply.

---

**[1]**

Original tweet:
> [paste here]

Your reply:
> [paste here]

---

**[2]**

Original tweet:
> [paste here]

Your reply:
> [paste here]

---

**[3]**

Original tweet:
> [paste here]

Your reply:
> [paste here]

---

**[4]**

Original tweet:
> [paste here]

Your reply:
> [paste here]

---

**[5]**

Original tweet:
> [paste here]

Your reply:
> [paste here]

---

**[6]**

Original tweet:
> [paste here]

Your reply:
> [paste here]

---

**[7]**

Original tweet:
> [paste here]

Your reply:
> [paste here]

---

**[8]**

Original tweet:
> [paste here]

Your reply:
> [paste here]

---

**[9]**

Original tweet:
> [paste here]

Your reply:
> [paste here]

---

**[10]**

Original tweet:
> [paste here]

Your reply:
> [paste here]

---

**[11]**

Original tweet:
> [paste here]

Your reply:
> [paste here]

---

**[12]**

Original tweet:
> [paste here]

Your reply:
> [paste here]

---

**[13]**

Original tweet:
> [paste here]

Your reply:
> [paste here]

---

**[14]**

Original tweet:
> [paste here]

Your reply:
> [paste here]

---

**[15]**

Original tweet:
> [paste here]

Your reply:
> [paste here]

---

## 5. how do you write — not vibes, actual patterns

Don't say "casual" or "authentic". Describe what you actually do.

Useful answers look like:
- "I usually add one data point the original tweet is missing"
- "I flip the framing and show why the opposite might also be true"
- "I never write more than 3 sentences"
- "I ask a follow-up question when I'm genuinely curious, not to seem engaged"
- "I reference specific protocols/companies/numbers, not abstractions"
- "I sometimes just post a one-liner reaction with no explanation"

> - [pattern 1]
> - [pattern 2]
> - [pattern 3]
> - [pattern 4]
> - [pattern 5]

---

## 6. your Tier 1 topics — the lanes you actually know

These are the topics where if you saw a tweet, you'd have something real to add.

List 5-10. Rule of thumb: could you write a 5-tweet thread about it right now without googling?

> [list them]

---

## 7. your Tier 2 topics — interesting but not your main thing

Adjacent topics you engage with when the take is interesting. You have opinions but you're not the expert.

> [list them]

---

## 8. accounts you want to engage with more

People in your space where a good reply could actually start something. Ideally in the 5k-100k follower range — big enough to matter, small enough that your reply gets seen.

> [list handles]

---

## 9. accounts to always skip

Anyone who keeps showing up in your feed that you never want to engage with — bots, noise accounts, mega-accounts where your reply just drowns.

Add these to `SKIP_AUTHORS` in `scripts/x_feed_monitor.py`.

> [list handles]

---

## Now compile your reply-style.md

Take everything above and build `prompts/reply-style.md`:

1. Paste your 15 reply pairs into the `## Examples` section (use the format in the template)
2. Write your voice notes using the patterns from question 5
3. Save the file

That's your voice guide. Claude reads it on every run.

**The more honest and specific you are, the better the suggestions.**

If a suggestion comes back and sounds wrong, come back here and ask: am I describing how I actually write, or how I *want* to write? Usually it's the second one.
