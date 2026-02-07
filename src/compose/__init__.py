# Response composition: tone, formatting, ops coach suggestions
from .templates import get_tone_profile, TONE_NEUTRAL, TONE_WITTY, TONE_MINIMAL
from .formatter import format_jobs_list_by_day, format_help_message, format_unknown_capabilities
from .suggestions import ops_coach_suggestions

__all__ = [
    "get_tone_profile",
    "TONE_NEUTRAL",
    "TONE_WITTY",
    "TONE_MINIMAL",
    "format_jobs_list_by_day",
    "format_help_message",
    "format_unknown_capabilities",
    "ops_coach_suggestions",
]
