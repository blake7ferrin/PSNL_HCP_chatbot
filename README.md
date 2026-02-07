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
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `HCP_API_KEY` | Yes | Housecall Pro API key (Bearer token) |
| `ALLOWED_TELEGRAM_IDS` | No | Comma-separated Telegram user IDs; if set, only these users can use the bot |
| `OPENAI_API_KEY` or `OPENROUTER_API_KEY` | No | If set, job-list answers use an LLM for natural-language summaries (OpenRouter preferred if both set) |
| `LLM_MODEL` | No | Model name (default: `gpt-4o-mini` for OpenAI; `openai/gpt-4o-mini` for OpenRouter) |

## Capabilities

The bot is **read-only**. It can answer questions about:

- **Jobs** – list jobs, job details (e.g. "today's jobs", "job 12345")
- **Estimates** – list estimates, estimate details
- **Customers** – list customers, customer details
- **Company** – company info (if supported by API)
- **Pricebook** – services/materials (if supported by API)
- **Schedule** – appointments/technicians (if supported by API)

No create, update, or delete operations are performed.

For exact API endpoint paths and response shapes, see the [Housecall Pro Public API documentation](https://docs.housecallpro.com/).
