"""Tone profiles for response composition. Configurable via COMPOSE_TONE env."""
import os
from typing import Callable

# Profile names (env: COMPOSE_TONE=neutral_professional | witty_confident | minimalist)
TONE_NEUTRAL = "neutral_professional"
TONE_WITTY = "witty_confident"
TONE_MINIMAL = "minimalist"

_PROFILES = {
    TONE_NEUTRAL: {
        "no_results": "No jobs found for that period.",
        "next_actions_header": "Suggested next steps:",
        "greeting": "Here’s what I found.",
    },
    TONE_WITTY: {
        "no_results": "Nothing on the board for that range.",
        "next_actions_header": "Want to dig deeper? Try:",
        "greeting": "Here you go.",
    },
    TONE_MINIMAL: {
        "no_results": "No jobs.",
        "next_actions_header": "Next:",
        "greeting": "",
    },
}


def get_tone_profile() -> str:
    """Return current tone profile name from env (default: neutral_professional)."""
    raw = (os.getenv("COMPOSE_TONE") or "").strip().lower()
    if raw in _PROFILES:
        return raw
    return TONE_NEUTRAL


def get_phrase(key: str) -> str:
    """Get a phrase for the current tone profile."""
    profile = get_tone_profile()
    return _PROFILES.get(profile, _PROFILES[TONE_NEUTRAL]).get(key, "")
