# DailyNews v2

A personal ML news triage bot. It pulls frontier-lab announcements, open-weight model releases, and a full day of arXiv. Each item gets classified with [Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) for a fraction of a cent, ranked by a model that learns from your 👍/👎, and delivered to your phone on **Telegram**. It runs on **GitHub Actions** with no server and no laptop.

```
hourly cron ─► sync 👍/👎 from Telegram ─► fetch due sources ─► dedup + cluster
           ─► Jev: kind · topic · significance · substantive   (heuristic fallback)
           ─► rank = prior + learned(your ratings) ─► quality floor + diversity caps
           ─► ⚡ breaking push (lab releases, outside quiet hours)
           ─► ☀️ morning digest (first run after 7:00 local, once a day)
           ─► encrypted SQLite snapshot → orphan `data` branch
```

## What changed from v1

| v1 | v2 |
|---|---|
| A generative LLM summarized *every* item | Jev only classifies (no text generation). Abstracts and descriptions are already summaries. |
| A generic 1–10 "relevance" score, mostly 5s and 6s | Calibrated probabilities feed into your interest weights (`config/profile.yaml`) |
| No learning | Logistic regression on your 👍/👎 phases in after 15 ratings (≥5 of each) |
| Newest 50 arXiv papers (an arbitrary slice) | About 400/run, all triaged |
| Anthropic feed silently broken | Listing pages scraped; any broken source shows up in the digest footer |
| Postgres, Ollama, FastAPI, Next.js, local cron | One Python package, SQLite, GitHub Actions, Telegram |

**Cost:** about 200–500 items/day × about 500 tokens comes to roughly **$0.15–0.40/month** at Jev's Oct 2026 price ($0.042/M input, free output). The digest footer reports the actual spend.

## Setup (about 10 minutes)

1. **Create the bot.** In Telegram, message [@BotFather](https://t.me/BotFather), send `/newbot`, and copy the token. Then send any message to your new bot.
2. **Get your chat ID.**
   ```bash
   pip install -e . && TELEGRAM_BOT_TOKEN=... python -m dailynews chat-id
   ```
3. **Add repo secrets** (Settings → Secrets and variables → Actions):
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - `TYPESAFE_API_KEY`
   - `STATE_KEY`: any long random string (`openssl rand -base64 32`). **Required on a public repo**: it encrypts your ratings and history on the `data` branch.
4. **Check everything.**
   ```bash
   TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... TYPESAFE_API_KEY=... python -m dailynews doctor --send-test
   ```
5. **Merge to the default branch.** Scheduled workflows only run there. Optionally trigger *Actions → dailynews → Run workflow* with `force_digest` checked.

## Instant taps + on-time schedule (Cloudflare Worker, optional, ~15 min)

A free Cloudflare Worker (`worker/`) becomes the bot's webhook. Each tap gets a "Saved 👍" popup and a ✓ within a second, and is stored until the next run collects it. The Worker's cron also triggers the `dailynews` workflow hourly at :23, because GitHub's own scheduler often runs hours late. GitHub's schedule stays as a backup every 3h.

1. **Cloudflare account.** Sign up at dash.cloudflare.com and open **Workers & Pages** once so it gives you a `workers.dev` subdomain. Copy your **Account ID**, shown on the right of that page.
2. **Cloudflare API token.** Go to My Profile → API Tokens → Create Token → use the **Edit Cloudflare Workers** template → choose your account → create it and copy the token.
3. **GitHub token for the hourly trigger.** Go to GitHub Settings → Developer settings → Fine-grained tokens → Generate. Set Repository access to *Only DailyNews* and Permissions to **Actions: Read and write**, with nothing else.
4. **Add three repo secrets:** `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `DISPATCH_TOKEN`.
5. **Deploy.** Go to Actions → **worker** → Run workflow (action: `deploy`). It tests, creates the KV store, deploys, sets the Worker's secrets, health-checks it, and points the bot at it. The run's annotation shows the live URL.

Nothing else needs copying. The webhook secret and the key the pipeline uses to read taps are derived from `STATE_KEY` + `TELEGRAM_BOT_TOKEN` on both sides, and the pipeline finds the Worker from the bot's webhook URL.

**To undo:** run the **worker** workflow with action `disable`. Telegram goes back to queueing taps, and the pipeline automatically returns to reading them with getUpdates. If you rotate `STATE_KEY` or the bot token, re-run `deploy`.

## Schedule

- **Digest every other morning** (`digest.every_days: 2`), first run after 7:00 local. It goes out once ≥ 2 days have passed since the last one, so a missed run sends the next morning instead of skipping a cycle.
- **Full sweep only before a digest:** arXiv (paged, up to 2,000 over 3 days), HF Daily Papers (one request per day), community feeds and hand-picked blogs.
- **Hourly between digests:** only the lab blogs/pages and HF releases ("fast" sources) are checked, for ⚡ breaking pushes. Set `tier: fast|full` on a source in `sources.yaml` to change this.
- **Reserved slots:** `digest.reserve` guarantees math/optimization a place when a good-enough item exists (`reserve_floor`).

## Using it

- **👍/👎** on any item trains the ranker. With the Cloudflare Worker installed (below), the button turns ✓ instantly. Without it, taps wait in Telegram's queue (24h max) until the next run collects them.
- **Tune** `config/profile.yaml`: topic weights, digest size, quality floor (`min_score`), quiet hours, and breaking thresholds. Editing a topic *description* or kind changes the Jev question set. Your rated items then get re-classified automatically (cost: pennies) so the ranker retrains on consistent features. Weight changes need no re-classification.
- **Sources** are in `config/sources.yaml`. Each has its own polling interval.
- **Local dry run:** `python -m dailynews run --dry-run --force-digest` prints messages instead of sending them.

## Design notes and edge cases

- **Lab priority is deterministic.** It comes from the source (an official blog, an HF org, an HF Daily Papers organization), never from a model guessing affiliation from abstract text.
- **Dedup and clustering.** Items are merged by arXiv ID (arXiv ↔ HF Papers, which also carries upvotes and lab attribution over), by HF release family (`-Instruct`, `-FP8`, `-GGUF`… collapse into one item), and by near-identical headlines across different sources.
- **First run.** A source's *undated* back catalogue (the scraped Anthropic pages) is stored as already seen, so you don't get flooded. Dated items are bounded by `max_age_days`.
- **No double sends.** State is saved even when a run fails (`if: always()`), runs never overlap (`concurrency`), and the save step refuses to push if the restore didn't succeed. A bad `STATE_KEY` can't wipe your history.
- **Jev outages.** 429/5xx are retried with `Retry-After`. Auth errors trip a circuit breaker, and the run continues on a keyword heuristic. Heuristic labels are replaced on the next healthy run and are never used as training data.
- **Pinned model.** `JEV_MODEL` defaults to `jev-1.13.0`, not `jev-latest`, because the ranker learns from Jev's output distribution. To upgrade, set the `JEV_MODEL` repo variable. Rated items aren't auto-re-classified on a model change, so expect a few days of drift.
- **Breaking pushes** require a frontier-lab source, P(release) ≥ 0.6, real significance, and age under 12h. They're capped per run, suppressed in quiet hours, and skipped when the digest is about to go out.
- **Quality floor.** On a slow day the digest is short rather than padded.
- **GitHub Actions caveats.** Scheduled runs can start late at busy times, and GitHub disables schedules on repos with 60 days of no activity. The hourly state push should count as activity, but if the digest ever stops, check the Actions tab. Reddit often blocks Actions IPs; if so, the footer will say so.

- **Taps (Worker mode):** the Worker accepts only requests carrying the webhook secret and only taps from `TELEGRAM_CHAT_ID`. The latest tap per item wins. The pipeline acknowledges a tap only after saving it, and the Worker deletes it only if it hasn't changed since the pull, so a re-tap mid-run survives. If the Worker is down, Telegram retries delivery, and the run notes the failure without breaking.

## Development

```bash
pip install -e '.[dev]'
pytest            # offline: fake feeds, fake Jev, fake Telegram, fake Worker, real git for state.sh
cd worker && npm ci && npm test   # Worker: fake KV + fake Telegram/GitHub
```
