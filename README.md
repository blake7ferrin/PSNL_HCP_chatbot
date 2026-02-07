# Polar Air HCP Chatbot

Internal read-only Telegram bot for Polar Air admin staff. Answers questions about scheduling, jobs, estimates, company setup, and pricebook using the Housecall Pro API.

## Prerequisites

- **Housecall Pro MAX plan** (API is only available on MAX).
- **Housecall Pro API key**: Housecall Pro App Store → API → View Details → Generate API Key (Admin only). See [Housecall Pro API docs](https://docs.housecallpro.com/).
- **Telegram Bot Token**: Create a bot via [@BotFather](https://t.me/BotFather).

## Setup

### Option A: Doppler (recommended)

1. [Install the Doppler CLI](https://docs.doppler.com/docs/install-cli) and log in: `doppler login`.
2. In this repo folder, run `doppler setup` and create/link a project (e.g. `polar-air-hcp-bot`). Choose a config (e.g. `dev`).
3. In the [Doppler dashboard](https://dashboard.doppler.com), add these secrets to your project:
   - `TELEGRAM_BOT_TOKEN` (required)
   - `HCP_API_KEY` (required)
   - `OPENAI_API_KEY` or `OPENROUTER_API_KEY` (optional, for LLM summaries)
   - `ALLOWED_TELEGRAM_IDS` (optional, comma-separated Telegram user IDs)
   - `LLM_MODEL` (optional)
4. Install Python deps and run with Doppler:

   ```bash
   pip install -r requirements.txt
   doppler run -- py run.py
   ```

### Option B: .env file

1. Copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN`, `HCP_API_KEY`, and any optional vars.
2. Install and run:

   ```bash
   pip install -r requirements.txt
   py run.py
   ```

   Or: `py -m src.main`

## Environment variables

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `HCP_API_KEY` | Yes | Housecall Pro API key (Bearer token) |
| `ALLOWED_TELEGRAM_IDS` | No | Comma-separated Telegram user IDs; if set, only these users can use the bot |
| `OPENAI_API_KEY` or `OPENROUTER_API_KEY` | No | If set, job-list answers use an LLM for natural-language summaries (OpenRouter preferred if both set) |
| `LLM_MODEL` | No | Model name (default: `gpt-4o-mini` for OpenAI; `openai/gpt-4o-mini` for OpenRouter) |
| `LLM_SUMMARIES_ENABLED` | No | Set to `0` or `false` to disable LLM summaries (deterministic formatting only) |
| `COMPOSE_TONE` | No | Response tone: `neutral_professional`, `witty_confident`, or `minimalist` |
| `HCP_API_BASE_URL` | No | Override Housecall Pro API base (default: `https://api.housecallpro.com`) |
| `HCP_API_VERSION_STRATEGY` | No | `public` (default, no prefix) or `legacy` (adds `/v1`) |
| `HCP_API_PREFIX` | No | Explicit API prefix override (e.g. `v1` or `housecall/v1`) |
| `BOT_DB_PATH` | No | SQLite DB path for memory/metrics (default: `./data/bot.db`) |
| `DEBUG` | No | Set to `1`, `true`, or `yes` for full logging (intent, HCP response keys, LLM success/failure) |

## Verify setup

Run with the same env as the bot (e.g. Doppler):

```bash
doppler run -- py check_env.py
```

This checks that `TELEGRAM_BOT_TOKEN` and `HCP_API_KEY` are set, and pings the Housecall Pro API. If you see **all 404** for HCP paths, the key may be valid but your account/plan may use different endpoint paths or base URL; set `HCP_API_BASE_URL` in Doppler if your docs specify another base. Requires **Housecall Pro MAX** plan for API access.

You can also use `/health` inside Telegram to see env status, HCP connectivity, and DB status (no secrets are shown).

## Data storage

Conversation state and daily metrics are stored in SQLite at `BOT_DB_PATH` (default: `./data/bot.db`). The DB is created automatically and uses WAL mode.

## Capabilities

The bot is **read-only**. It can answer questions about:

- **Jobs** – list jobs by date range (e.g. "today", "next week", "any day next week", "Tuesday"), job details by ID or "the second one"
- **Estimates** – list estimates, estimate details
- **Customers** – list customers, customer details
- **Company** – company info (if supported by API)
- **Pricebook** – services/materials (if supported by API)
- **Schedule** – same as jobs list for a date range
- **Stats** – quick counts (jobs today, this week, estimates, customers)

No create, update, or delete operations are performed.

For exact API endpoint paths and response shapes, see the [Housecall Pro Public API documentation](https://docs.housecallpro.com/).

---

## How intent routing works

User messages are mapped to **intents** (e.g. `jobs.list`, `job.get`, `estimates.list`, `help`) by the **router** in `src/intents/router.py`. The router is **deterministic**: it uses keyword/phrase rules and regex, not an LLM.

1. **Input**: Raw message text + optional **context** from per-chat memory (last intent, last date range, last list of entity IDs).
2. **Order of checks**: Help → get-by-id (job, estimate, customer) → "the second one" resolution from last list → date range + jobs/schedule → stats → company → pricebook → estimates → customers → jobs (default today) → unknown.
3. **Date parsing**: Phrases like "today", "next week", "this weekend", "Tuesday" (or "what about Tuesday?" after "next week") are parsed in `src/intents/dateparse.py` into a start/end date in the user’s timezone (default `America/Phoenix`).
4. **Output**: An `Intent` (name + optional filters like date range, optional entity_id for get-by-id). Handlers in `src/telegram/handlers.py` call the HCP API and the compose layer to format the reply.

---

## Confirmations

When the bot asks a follow-up that implies an action (e.g. “Want me to list jobs from last week?”), you can reply with a confirmation like **yes**, **yes please**, **ok**, or **sure**. The bot will execute the suggested action. If there’s no pending action, it will ask a short clarifying question.

---

## How to add a new intent

1. **Schema** (`src/intents/schema.py`): Add a constant, e.g. `INTENT_MY_FEATURE = "my_feature"`.
2. **Router** (`src/intents/router.py`): Add keyword/phrase checks and return `Intent(INTENT_MY_FEATURE, ...)` in the right place (before the generic fallbacks). If the intent needs a date range, use `parse_human_date(...)` and set `filters.start_date` / `filters.end_date`.
3. **Handler** (`src/telegram/handlers.py`): In `_dispatch()`, add a branch for `intent.name == INTENT_MY_FEATURE`: call the right HCP module (or `src/hcp/endpoints.py`), then format the reply (e.g. via `src/compose/formatter.py` or `src/bot/responses.py`).
4. **Optional**: Add a tone phrase in `src/compose/templates.py` and use it in the formatter. Add Ops Coach suggestions in `src/compose/suggestions.py` if the response is a list.

---

## How to configure tone profile

Set the env var **`COMPOSE_TONE`** to one of:

- **`neutral_professional`** (default) – e.g. "No jobs found for that period.", "Suggested next steps:"
- **`witty_confident`** – e.g. "Nothing on the board for that range.", "Want to dig deeper? Try:"
- **`minimalist`** – e.g. "No jobs.", "Next:"

Phrases are defined in `src/compose/templates.py`. Only a few strings are tone-dependent (no-results message, next-actions header, greeting); the rest of the reply is the same. To add a new profile, add an entry to the `_PROFILES` dict and use `get_phrase(key)` in the formatter.
