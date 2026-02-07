"""Tests for conversational UX: no-total, aggregation, fallback copy (no hallucination)."""
import pytest
from datetime import date

from src.bot.responses import format_job_total_only
from src.compose.formatter import format_aggregation_unsupported, format_unknown_capabilities


def test_no_total_includes_explanation_and_suggestion():
    """When job has no total, response explains why and suggests next step (no fabricated totals)."""
    job_no_total = {"id": "job-xyz", "status": "scheduled"}
    out = format_job_total_only(job_no_total)
    assert "doesn't have a total" in out or "hasn't been invoiced" in out
    assert "estimate" in out.lower() or "invoices" in out.lower() or "completed" in out.lower()
    assert "No total amount on file" not in out


def test_no_total_wrapped_in_job_key():
    """format_job_total_only unwraps {'job': {...}}; no total still gives explanation + suggestion."""
    out = format_job_total_only({"job": {"id": "j1", "status": "completed"}})
    assert "doesn't have a total" in out or "hasn't been invoiced" in out
    assert "estimate" in out.lower() or "invoices" in out.lower()


def test_aggregation_unsupported_explanation_and_alternatives_no_job_list():
    """Aggregation unsupported message explains why, offers alternatives, one suggestion; no raw job list."""
    msg = format_aggregation_unsupported(
        "last week",
        start_date=date(2026, 1, 26),
        end_date=date(2026, 1, 30),
    )
    assert "can't calculate" in msg or "doesn't expose" in msg
    assert "Housecall Pro" in msg or "collected total" in msg
    assert "list jobs" in msg or "invoice totals" in msg
    assert "Want me to" in msg or "list jobs" in msg
    # Must not contain a job list (no "*Job #" or "• Job" style dump)
    assert "*Job #" not in msg
    assert "Jan 26" in msg or "Jan 30" in msg


def test_aggregation_unsupported_without_dates_still_helpful():
    """When only date_label is given, message is still helpful (no date range in parens)."""
    msg = format_aggregation_unsupported("that period")
    assert "can't calculate" in msg or "doesn't expose" in msg
    assert "list jobs" in msg or "invoice" in msg


def test_fallback_confident_tone():
    """Unknown intent fallback is confident ('what I can help with'), not apologetic."""
    msg = format_unknown_capabilities(with_buttons_hint=False)
    assert "can't calculate that directly" in msg or "can* help with" in msg
    assert "I didn't quite get that" not in msg
    assert "Jobs today" in msg or "List estimates" in msg
