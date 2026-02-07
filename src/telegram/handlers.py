"""Telegram message handlers: auth, intent routing, HCP fetch, compose, reply."""
import logging
import os
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from src.intents import route, Intent, IntentFilters
from src.intents.schema import (
    INTENT_JOBS_LIST,
    INTENT_JOB_GET,
    INTENT_JOB_TIME,
    INTENT_ESTIMATES_LIST,
    INTENT_ESTIMATE_GET,
    INTENT_CUSTOMERS_SEARCH,
    INTENT_CUSTOMER_GET,
    INTENT_PRICEBOOK_SEARCH,
    INTENT_COMPANY_INFO,
    INTENT_STATS,
    INTENT_HELP,
    INTENT_AGGREGATION_UNSUPPORTED,
    INTENT_UNKNOWN,
)
from src.memory import get_chat_memory
from src.hcp.client import HCPClientError
from src.hcp import jobs as hcp_jobs
from src.hcp import estimates as hcp_estimates
from src.hcp import customers as hcp_customers
from src.hcp import pricebook as hcp_pricebook
from src.hcp import company as hcp_company
from src.hcp import endpoints  # for list_appointments, list_employees, count_jobs_in_date_range
from src.compose.formatter import (
    format_jobs_list_by_day,
    format_help_message,
    format_unknown_capabilities,
    format_aggregation_unsupported,
    extract_job_ids_from_list,
)
from src.compose.templates import get_phrase
from src.bot import responses  # legacy format_* for estimates/customers/company/pricebook/error


def _is_llm_summaries_enabled() -> bool:
    raw = os.getenv("LLM_SUMMARIES_ENABLED", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _is_allowed(user_id: int | None) -> bool:
    allowed = os.getenv("ALLOWED_TELEGRAM_IDS", "").strip()
    if not allowed:
        return True
    if user_id is None:
        return False
    return str(user_id) in [s.strip() for s in allowed.split(",") if s.strip()]


def _denial_message() -> str:
    return (
        "You’re not on the access list for this bot. "
        "Ask your admin to add your Telegram user ID to ALLOWED_TELEGRAM_IDS. "
        "Send /whoami to another bot to get your ID, or ask the admin to run this bot with the list unset for testing."
    )


async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start and /help."""
    if not update.message:
        return
    user_id = update.effective_user.id if update.effective_user else None
    if not _is_allowed(user_id):
        await update.message.reply_text(_denial_message())
        return
    await update.message.reply_text(format_help_message(), parse_mode="Markdown")


async def handle_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with the user's Telegram ID for allow-list setup."""
    if not update.message:
        return
    user_id = update.effective_user.id if update.effective_user else None
    if not _is_allowed(user_id):
        await update.message.reply_text(_denial_message())
        return
    uid = user_id if user_id is not None else "?"
    await update.message.reply_text(
        f"Your Telegram user ID: `{uid}`\nAdd this to ALLOWED_TELEGRAM_IDS to grant access.",
        parse_mode="Markdown",
    )


def _filters_to_dates(f: IntentFilters) -> tuple[str | None, str | None]:
    start = f.start_date
    end = f.end_date or start
    if start is None:
        return None, None
    return start.isoformat() if isinstance(start, date) else str(start), (end.isoformat() if isinstance(end, date) else str(end)) if end else None


# Reference phrases that refer to the last list/job (conversation anchor)
_REFERENCE_PHRASES = (
    "that one",
    "the one",
    "that job",
    "next week's job",
    "the job next week",
    "next weeks job",
    "next weeks",
)
# Follow-up intents that implicitly refer to last job when anchor has single id
_TOTAL_DETAILS_PHRASES = ("total", "details", "info", "amount", "cost", "price", "show job")
# "Total collected last week" / "our total this week" = period aggregate, not "that job's total"
_PERIOD_AGGREGATE_PHRASES = ("collected", "revenue", "our total", "we collected", "total for the week", "total for last")


def _should_inject_resolved_entity(text: str, anchor: dict) -> bool:
    """
    True if we should inject resolved_entity into context.
    - Reference phrase (that one, next week's job, etc.) + anchor exists
    - OR total/details/amount + anchor exists with exactly 1 job
    - EXCEPT when user asks for period aggregate (e.g. "total collected last week")
    """
    if not anchor:
        return False
    ids = anchor.get("ids") or []
    lower = text.lower().strip()
    if any(p in lower for p in _PERIOD_AGGREGATE_PHRASES):
        period_words = ("last week", "this week", "next week", "today", "yesterday", "this month", "last month")
        if any(p in lower for p in period_words):
            return False
    if any(p in lower for p in _REFERENCE_PHRASES):
        return True
    if len(ids) == 1 and any(p in lower for p in _TOTAL_DETAILS_PHRASES):
        return True
    return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route message -> intent -> HCP -> compose -> reply; update memory."""
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not _is_allowed(user_id):
        await update.message.reply_text(_denial_message())
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is None:
        return

    text = update.message.text.strip()
    if text.startswith("/"):
        return

    memory = get_chat_memory(str(chat_id))
    ctx = memory.to_context()
    # Pre-route: inject resolved_entity when user references last job and we have anchor
    anchor = memory.get_anchor()
    if _should_inject_resolved_entity(text, anchor):
        date_range = anchor.get("date_range")
        if date_range and isinstance(date_range, (list, tuple)) and len(date_range) >= 2:
            s, e = date_range[0], date_range[1]
            ctx["resolved_entity"] = {
                "type": anchor.get("type") or "job",
                "ids": list(anchor.get("ids") or []),
                "date_range": (s, e),
            }
        else:
            ctx["resolved_entity"] = {
                "type": anchor.get("type") or "job",
                "ids": list(anchor.get("ids") or []),
                "date_range": None,
            }
    elif any(p in text.lower() for p in _REFERENCE_PHRASES) and not anchor:
        ctx["reference_phrase_used"] = True
    intent = route(text, context=ctx, tz_name=memory.timezone)
    logger.debug("message=%r -> intent=%s entity_id=%s filters=%s", text[:80], intent.name, getattr(intent, "entity_id", None), getattr(intent.filters, "date_label", None) or getattr(intent.filters, "status", None))

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    tz_name = memory.timezone
    try:
        reply, use_markdown, entity_ids = await _dispatch(intent, text, tz_name=tz_name)
    except HCPClientError as e:
        reply = responses.format_error(str(e))
        use_markdown = True
        entity_ids = None
    except Exception as e:
        logger.exception("Handler error: %s", e)
        reply = responses.format_error(str(e))
        use_markdown = True
        entity_ids = None

    # Write anchor after successful entity responses; clear on topic change
    if entity_ids is not None and intent.name == INTENT_JOBS_LIST:
        start_d = intent.filters.start_date
        end_d = intent.filters.end_date or start_d
        date_range = (start_d, end_d) if start_d and end_d else None
        memory.set_anchor(
            "job",
            ids=entity_ids,
            date_range=date_range,
            label=intent.filters.date_label or "",
        )
        memory.update_after_intent(
            intent.name,
            start_date=start_d,
            end_date=end_d,
            date_label=intent.filters.date_label or "",
        )
    elif intent.name == INTENT_JOBS_LIST and (intent.filters.start_date or intent.filters.end_date):
        memory.update_after_intent(
            intent.name,
            start_date=intent.filters.start_date,
            end_date=intent.filters.end_date,
            date_label=intent.filters.date_label or "",
        )
    elif intent.name == INTENT_JOB_GET and intent.entity_id:
        memory.set_anchor("job", [intent.entity_id])
        memory.update_after_intent(intent.name, entity_type="job", entity_id=intent.entity_id)
    elif intent.name in (
        INTENT_ESTIMATES_LIST,
        INTENT_ESTIMATE_GET,
        INTENT_CUSTOMERS_SEARCH,
        INTENT_CUSTOMER_GET,
        INTENT_HELP,
        INTENT_COMPANY_INFO,
        INTENT_PRICEBOOK_SEARCH,
        INTENT_STATS,
    ):
        memory.clear_anchor()

    try:
        await update.message.reply_text(reply or "Something went wrong.", parse_mode="Markdown" if use_markdown else None)
    except Exception as e:
        logger.exception("Failed to send reply: %s", e)
        try:
            await update.message.reply_text("Something went wrong. Check the bot logs.")
        except Exception:
            pass


async def _dispatch(intent: Intent, user_message: str, *, tz_name: str = "America/Phoenix") -> tuple[str, bool, list[str] | None]:
    """Call HCP, format reply. Returns (reply_text, use_markdown, entity_ids or None)."""
    if intent.name == INTENT_HELP:
        return format_help_message(), True, None

    if intent.name == INTENT_UNKNOWN:
        clarification = (intent.raw_slots or {}).get("clarification")
        if clarification == "multiple_jobs":
            return "I see multiple jobs. Do you mean the first or second one?", True, None
        if clarification == "no_job":
            return (
                "I don't see a job list in context. Ask for a list first, then you can say \"the second one\" or \"details\".\n\n"
                "Try: _Jobs today_, _Jobs next week_, or _Last week_."
            ), True, None
        hint = intent.raw_slots.get("hint") if intent.raw_slots else None
        if hint:
            return hint + "\n\n" + format_unknown_capabilities(with_buttons_hint=False), True, None
        return format_unknown_capabilities(with_buttons_hint=False), True, None

    # ---- aggregation unsupported (total collected / revenue for period: explain + alternatives, no job dump) ----
    if intent.name == INTENT_AGGREGATION_UNSUPPORTED:
        f = intent.filters
        date_label = (f.date_label or "that period").strip() or "that period"
        start_d = getattr(f, "start_date", None)
        end_d = getattr(f, "end_date", None)
        reply = format_aggregation_unsupported(date_label, start_date=start_d, end_date=end_d)
        return reply, True, None

    # ---- jobs.list (always deterministic format so times are in user TZ, no UTC leak) ----
    if intent.name == INTENT_JOBS_LIST:
        f = intent.filters
        start_iso, end_iso = _filters_to_dates(f)
        date_label = f.date_label or (start_iso or "today")
        if start_iso and end_iso and start_iso != end_iso:
            data = await hcp_jobs.list_jobs(start_date=start_iso, end_date=end_iso)
        else:
            data = await hcp_jobs.list_jobs(scheduled_start_date=start_iso or None)
        jobs_list = _list_from_response(data)
        logger.debug("jobs.list: response keys=%s jobs_count=%d", list(data.keys()) if isinstance(data, dict) else "raw", len(jobs_list))
        ids = extract_job_ids_from_list(data)
        reply = format_jobs_list_by_day(data, date_label, include_suggestions=True, tz_name=tz_name)
        return reply, True, ids

    # ---- job.get (always use deterministic format for correct money + timezone) ----
    if intent.name == INTENT_JOB_GET and intent.entity_id:
        data = await hcp_jobs.get_job(intent.entity_id)
        if getattr(intent, "focus", None) == "money":
            return responses.format_job_total_only(data), True, None
        return responses.format_job_detail(data, tz_name=tz_name), True, None

    # ---- job.time (what time is it at? for last job) ----
    if intent.name == INTENT_JOB_TIME and intent.entity_id:
        data = await hcp_jobs.get_job(intent.entity_id)
        return responses.format_job_time_only(data, tz_name=tz_name), True, None

    # ---- estimates.list ----
    if intent.name == INTENT_ESTIMATES_LIST:
        status_filter = intent.filters.status if intent.filters else None
        data = await hcp_estimates.list_estimates(status=status_filter)
        list_label = None
        if status_filter == "unscheduled":
            list_label = "unscheduled estimates"
        elif status_filter == "open":
            list_label = "open estimates"
        return responses.format_estimates_list(data, list_label=list_label), True, None

    # ---- estimate.get ----
    if intent.name == INTENT_ESTIMATE_GET and intent.entity_id:
        data = await hcp_estimates.get_estimate(intent.entity_id)
        if _is_llm_summaries_enabled():
            from src import llm
            if llm.is_available():
                summary = await llm.format_response("estimate_detail", data, user_message=user_message)
                if summary:
                    logger.debug("estimate.get: using LLM summary")
                    return summary, False, None
                logger.debug("estimate.get: LLM returned None, using deterministic format")
        return responses.format_estimate_detail(data), True, None

    # ---- customers.search (list) ----
    if intent.name == INTENT_CUSTOMERS_SEARCH:
        data = await hcp_customers.list_customers()
        return responses.format_customers_list(data), True, None

    # ---- customer.get ----
    if intent.name == INTENT_CUSTOMER_GET and intent.entity_id:
        data = await hcp_customers.get_customer(intent.entity_id)
        if _is_llm_summaries_enabled():
            from src import llm
            if llm.is_available():
                summary = await llm.format_response("customer_detail", data, user_message=user_message)
                if summary:
                    logger.debug("customer.get: using LLM summary")
                    return summary, False, None
                logger.debug("customer.get: LLM returned None, using deterministic format")
        return responses.format_customer_detail(data), True, None

    # ---- pricebook.search ----
    if intent.name == INTENT_PRICEBOOK_SEARCH:
        services = await hcp_pricebook.list_services()
        materials = await hcp_pricebook.list_materials()
        parts = []
        if services and _list_from_response(services):
            parts.append(responses.format_services_list(services))
        if materials and _list_from_response(materials):
            parts.append(responses.format_materials_list(materials))
        if not parts:
            return "Pricebook data is not available or empty.", True, None
        return "\n\n".join(parts), True, None

    # ---- company.info ----
    if intent.name == INTENT_COMPANY_INFO:
        data = await hcp_company.get_company()
        return responses.format_company(data), True, None

    # ---- stats ----
    if intent.name == INTENT_STATS:
        from datetime import date, timedelta
        today = date.today().isoformat()
        week_start = date.today() - timedelta(days=date.today().weekday())
        week_end = week_start + timedelta(days=6)
        jobs_today_data = await endpoints.list_jobs(scheduled_start_date=today)
        jobs_today = len(_list_from_response(jobs_today_data))
        jobs_this_week = await endpoints.count_jobs_in_date_range(week_start.isoformat(), week_end.isoformat())
        estimates_data = await endpoints.list_estimates(per_page=500)
        customers_data = await endpoints.list_customers(per_page=500)
        counts = {
            "jobs_today": jobs_today,
            "jobs_this_week": jobs_this_week,
            "estimates": len(_list_from_response(estimates_data)),
            "customers": len(_list_from_response(customers_data)),
        }
        return responses.format_stats(counts), True, None

    return format_unknown_capabilities(with_buttons_hint=False), True, None


def _list_from_response(data: Any) -> list:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("jobs", "estimates", "customers", "services", "materials", "data", "items", "results"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []
