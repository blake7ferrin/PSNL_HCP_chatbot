"""Check env and connectivity for the Polar Air HCP bot.
Run with same env as the bot, e.g.: doppler run -- py check_env.py
Or: py check_env.py (uses .env if present)
"""
import asyncio
import os
import sys
from pathlib import Path

# Match run.py: load .env if token not set (Doppler may have set it already)
if not os.getenv("TELEGRAM_BOT_TOKEN"):
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent / ".env")
        load_dotenv(Path.cwd() / ".env")
    except ImportError:
        pass


def main() -> None:
    ok = True

    # Required
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN: not set")
        ok = False
    else:
        print("TELEGRAM_BOT_TOKEN: set (length {})".format(len(token)))

    hcp_key = os.getenv("HCP_API_KEY", "").strip()
    from src.hcp.config import get_hcp_config
    cfg = get_hcp_config()
    hcp_base = cfg.base_url
    if not hcp_key:
        print("HCP_API_KEY: not set (bot will fail on jobs/estimates/customers)")
        ok = False
    else:
        print("HCP_API_KEY: set (length {})".format(len(hcp_key)))
    print("HCP_API_BASE_URL: {}".format(hcp_base))
    print("HCP_API_PREFIX: {}".format(cfg.api_prefix or "(public)"))

    # Access control
    allowed = os.getenv("ALLOWED_TELEGRAM_IDS", "").strip()
    if allowed:
        ids = [s.strip() for s in allowed.split(",") if s.strip()]
        print("ALLOWED_TELEGRAM_IDS: {} ID(s) (only these users can use the bot)".format(len(ids)))
    else:
        print("ALLOWED_TELEGRAM_IDS: not set (all users allowed)")

    # Optional LLM (estimate/customer detail summaries)
    openai = os.getenv("OPENAI_API_KEY", "").strip()
    openrouter = os.getenv("OPENROUTER_API_KEY", "").strip()
    llm_enabled = os.getenv("LLM_SUMMARIES_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")
    if openrouter:
        print("LLM: OpenRouter (OPENROUTER_API_KEY set, model=%s)" % (os.getenv("LLM_MODEL", "").strip() or "openai/gpt-4o-mini"))
    elif openai:
        print("LLM: OpenAI (OPENAI_API_KEY set, model=%s)" % (os.getenv("LLM_MODEL", "").strip() or "gpt-4o-mini"))
    else:
        print("LLM: not configured (no OPENAI_API_KEY or OPENROUTER_API_KEY; deterministic replies only)")
    if (openai or openrouter) and not llm_enabled:
        print("LLM_SUMMARIES_ENABLED: off (summaries disabled)")

    if not ok:
        print("\nFix missing vars in Doppler or .env, then run again.")
        sys.exit(1)

    # HCP API check: use explicit discovery probe
    if hcp_key:
        async def ping_hcp() -> bool:
            from src.hcp.discovery import probe_endpoints
            print("\nPinging Housecall Pro API (configured prefix only)...")
            result = await probe_endpoints()
            if result.ok:
                print("  Probe OK (prefix={})".format(cfg.api_prefix or "public"))
                return True
            if result.reason == "auth":
                print("  HCP API: 401 Unauthorized (invalid or expired API key)")
            elif result.reason == "endpoint_not_found":
                print("  HCP API: endpoint not found (check MAX plan, base URL, or prefix)")
            elif result.reason == "rate_limited":
                print("  HCP API: rate limit hit")
            else:
                print("  HCP API: probe failed (reason={})".format(result.reason))
            return False

        if not asyncio.run(ping_hcp()):
            ok = False

    # Optional: test LLM if keys set (surfaces bad key / quota errors)
    if (openai or openrouter) and ok:
        async def ping_llm():
            try:
                from src import llm
                if not llm.is_available():
                    print("\nLLM: client not available (key may be empty after load)")
                    return False
                # Minimal completion to verify key works
                client, model = llm._get_client()
                r = await client.chat.completions.create(model=model, messages=[{"role": "user", "content": "Say OK"}], max_tokens=10)
                out = (r.choices[0].message.content or "").strip()
                print("\nLLM: test completion OK (model=%s)" % model)
                return True
            except Exception as e:
                print("\nLLM: test failed: %s" % e)
                return False
        if not asyncio.run(ping_llm()):
            ok = False

    if ok:
        print("\nEnv and connectivity look good.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
