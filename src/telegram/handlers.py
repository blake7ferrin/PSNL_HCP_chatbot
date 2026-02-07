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
    INTENT_CONFIRM,
    INTENT_UNKNOWN,
)
from src.memory import AnchorDateRange, PendingAction, get_chat_memory, save_chat_memory
from src.hcp.client import HCPClientError
from src.hcp import jobs as hcp_jobs
from src.hcp import estimates as hcp_estimates
from src.hcp import customers as hcp_customers
from src.hcp import pricebook as hcp_pricebook
from src.hcp import company as hcp_company
from src.hcp import endpoints  # for list_appointments, list_employees, count_jobs_in_date_range
from src.hcp.config import get_hcp_config
from src.hcp.discovery import probe_endpoints
from src.compose.formatter import (
    format_jobs_list_by_day,
    format_help_message,
    format_unknown_capabilities,
    format_aggregation_unsupported,
    extract_job_ids_from_list,
    extract_entity_ids_from_list,
)
from src.bot import responses  # legacy format_* for estimates/customers/company/pricebook/error
from src.metrics.daily import record_jobs_list, record_estimates_list
from src.memory.sqlite_store import get_db_status
from src.utils.logging_utils import log_event


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


async def handle_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Report env, HCP probe, and DB status (safe, no secrets)."""
    if not update.message:
        return
    user_id = update.effective_user.id if update.effective_user else None
    if not _is_allowed(user_id):
        await update.message.reply_text(_denial_message())
        return
    cfg = get_hcp_config()
    token_set = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
    hcp_set = bool(os.getenv("HCP_API_KEY"))
    probe = None
    if hcp_set:
        probe = await probe_endpoints()
    db_status = get_db_status()
    lines = [
        "*Health*",
        "• Bot: ok",
        f"• Telegram token: {'set' if token_set else 'missing'}",
        f"• HCP API key: {'set' if hcp_set else 'missing'}",
        f"• HCP base URL: {cfg.base_url}",
        f"• HCP prefix: {cfg.api_prefix or 'public'}",
    ]
    if probe:
        status = "ok" if probe.ok else probe.reason
        lines.append(f"• HCP probe: {status}")
    else:
        lines.append("• HCP probe: skipped (missing API key)")
    if db_status.get("ok"):
        lines.append(f"• DB: ok (schema v{db_status.get('schema_version', 0)})")
    else:
        lines.append("• DB: error")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def _filters_to_dates(f: IntentFilters) -> tuple[str | None, str | None]:
    start = f.start_date
    end = f.end_date or start
    if start is None:
        return None, None
    return start.isoformat() if isinstance(start, date) else str(start), (end.isoformat() if isinstance(end, date) else str(end)) if end else None


def _pending_action_for_aggregation(f: IntentFilters) -> PendingAction | None:
    if not f.start_date:
        return None
    end = f.end_date or f.start_date
    params = {
        "start_date": f.start_date.isoformat(),
        "end_date": end.isoformat(),
        "date_label": f.date_label or "",
    }
    return PendingAction(intent_type=INTENT_JOBS_LIST, params=params, label=f.date_label or None)


def _intent_from_pending_action(action: PendingAction | dict[str, Any]) -> Intent:
    # Backward compatibility: old flow stores {"intent": "jobs.list", "filters": IntentFilters(...)}
    if isinstance(action, dict):
        if action.get("intent") == INTENT_JOBS_LIST and isinstance(action.get("filters"), IntentFilters):
            return Intent(INTENT_JOBS_LIST, filters=action["filters"])
        parsed = PendingAction.from_dict(action)
        if parsed is None:
            return Intent(INTENT_UNKNOWN, confidence=0.0)
        action = parsed
    if action.intent_type == INTENT_JOBS_LIST:
        filters = IntentFilters()
        start_raw = action.params.get("start_date")
        end_raw = action.params.get("end_date")
        if start_raw:
            filters.start_date = date.fromisoformat(str(start_raw))
        if end_raw:
            filters.end_date = date.fromisoformat(str(end_raw))
        filters.date_label = action.params.get("date_label") or None
        return Intent(INTENT_JOBS_LIST, filters=filters)
    return Intent(INTENT_UNKNOWN, confidence=0.0)


def _anchor_to_dict(memory: Any) -> dict[str, Any] | None:
    anchor = getattr(memory, "last_anchor", None)
    if isinstance(anchor, dict):
        return anchor
    if anchor and hasattr(anchor, "to_dict"):
        return anchor.to_dict()
    if hasattr(memory, "get_anchor"):
        got = memory.get_anchor()
        if isinstance(got, dict):
            return got
    return None


# Type-specific reference phrases: only inject when anchor type matches.
_REFERENCE_JOB = ("that job", "the job", "next week's job", "the job next week", "next weeks job", "next weeks")
_REFERENCE_CUSTOMER = ("that customer", "the customer")
_REFERENCE_ESTIMATE = ("that estimate", "the estimate")
_REFERENCE_ANY = ("that one", "the one")
_REFERENCE_PHRASES = _REFERENCE_JOB + _REFERENCE_CUSTOMER + _REFERENCE_ESTIMATE + _REFERENCE_ANY
_TOTAL_DETAILS_PHRASES = ("total", "details", "info", "amount", "cost", "price", "show job")
_PERIOD_AGGREGATE_PHRASES = ("collected", "revenue", "our total", "we collected", "total for the week", "total for last")


def _should_inject_resolved_entity(text: str, anchor: dict) -> bool:
    """
    True only when reference phrase matches anchor type (job/customer/estimate).
    "That job" -> anchor.type must be "job". "That one" -> any. Prevents resolving to wrong entity type.
    """
    if not anchor:
        return False
    anchor_type = anchor.get("type") or "job"
    ids = anchor.get("ids") or []
    lower = text.lower().strip()
    if any(p in lower for p in _PERIOD_AGGREGATE_PHRASES):
        period_words = ("last week", "this week", "next week", "today", "yesterday", "this month", "last month")
        if any(p in lower for p in period_words):
            return False
    if any(p in lower for p in _REFERENCE_JOB):
        return anchor_type == "job"
    if any(p in lower for p in _REFERENCE_CUSTOMER):
        return anchor_type == "customer"
    if any(p in lower for p in _REFERENCE_ESTIMATE):
        return anchor_type == "estimate"
    if any(p in lower for p in _REFERENCE_ANY):
        return True
    if len(ids) == 1 and any(p in lower for p in _TOTAL_DETAILS_PHRASES):
        return anchor_type == "job"
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
    anchor = _anchor_to_dict(memory)
    if _should_inject_resolved_entity(text, anchor or {}):
        date_range = anchor.get("date_range") if anchor else None
        if isinstance(date_range, dict):
            s, e = date_range.get("start"), date_range.get("end")
        else:
            s, e = None, None
        ctx["resolved_entity"] = {
            "type": (anchor or {}).get("type") or "job",
            "ids": list((anchor or {}).get("ids") or []),
            "date_range": (s, e) if s and e else None,
        }
    elif any(p in text.lower() for p in _REFERENCE_PHRASES) and not anchor:
        ctx["reference_phrase_used"] = True
    intent = route(text, context=ctx, tz_name=memory.timezone)
    log_event(
        logger,
        "intent_routed",
        level=logging.DEBUG,
        chat_id=str(chat_id),
        intent=intent.name,
        entity_id=getattr(intent, "entity_id", None),
        date_label=getattr(intent.filters, "date_label", None),
        status=getattr(intent.filters, "status", None),
        has_anchor=bool(memory.last_anchor),
    )

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    tz_name = memory.timezone
    # Confirm intent: execute pending action if present
    if intent.name == INTENT_CONFIRM:
        if memory.pending_action:
            pending = memory.pending_action
            memory.clear_pending_action()
            intent = _intent_from_pending_action(pending)
        else:
            reply = "What should I do next? Try: _Jobs today_ or _Jobs next week_."
            use_markdown = True
            entity_ids = None
            save_chat_memory(memory)
            try:
                await update.message.reply_text(reply, parse_mode="Markdown")
            except Exception as e:
                logger.exception("Failed to send reply: %s", e)
            return

    # Clear pending action on new non-confirm intents
    if intent.name != INTENT_CONFIRM and memory.pending_action:
        memory.clear_pending_action()

    try:
        reply, use_markdown, entity_ids = await _dispatch(intent, text, memory=memory, tz_name=tz_name)
    except HCPClientError as e:
        log_event(logger, "hcp_error", level=logging.WARNING, error=str(e), status_code=getattr(e, "status_code", None))
        if getattr(e, "status_code", None) == 429:
            reply = "HCP rate limit hit, try again shortly."
            use_markdown = False
        else:
            reply = responses.format_error(str(e))
            use_markdown = True
        entity_ids = None
    except Exception as e:
        log_event(logger, "handler_error", level=logging.ERROR, error=str(e))
        reply = responses.format_error(str(e))
        use_markdown = True
        entity_ids = None

    # Write anchor after successful entity responses; clear on topic change
    if entity_ids is not None and intent.name == INTENT_JOBS_LIST:
        start_d = intent.filters.start_date
        end_d = intent.filters.end_date or start_d
        date_range = AnchorDateRange(start=start_d, end=end_d) if start_d and end_d else None
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
    elif intent.name == INTENT_CUSTOMERS_SEARCH and entity_ids is not None:
        memory.set_anchor("customer", entity_ids)
        memory.update_after_intent(intent.name)
    elif intent.name == INTENT_CUSTOMER_GET and intent.entity_id:
        memory.set_anchor("customer", [intent.entity_id])
        memory.update_after_intent(intent.name, entity_type="customer", entity_id=intent.entity_id)
    elif intent.name == INTENT_ESTIMATES_LIST and entity_ids is not None:
        memory.set_anchor("estimate", entity_ids)
        memory.update_after_intent(intent.name)
    elif intent.name == INTENT_ESTIMATE_GET and intent.entity_id:
        memory.set_anchor("estimate", [intent.entity_id])
        memory.update_after_intent(intent.name, entity_type="estimate", entity_id=intent.entity_id)
    elif intent.name in (
        INTENT_HELP,
        INTENT_COMPANY_INFO,
        INTENT_PRICEBOOK_SEARCH,
        INTENT_STATS,
    ):
        memory.clear_anchor()

    # Pending action for aggregation clarifications
    if intent.name == INTENT_AGGREGATION_UNSUPPORTED:
        pending = _pending_action_for_aggregation(intent.filters)
        memory.set_pending_action(pending)

    save_chat_memory(memory)
    try:
        await update.message.reply_text(reply or "Something went wrong.", parse_mode="Markdown" if use_markdown else None)
    except Exception as e:
        log_event(logger, "reply_send_failed", level=logging.ERROR, error=str(e))
        try:
            await update.message.reply_text("Something went wrong. Check the bot logs.")
        except Exception:
            pass


def _anchor_type_mismatch_message(expected: str) -> str:
    """Graceful message when user said e.g. 'that job' but context is customer/estimate."""
    return "I lost track of the job. Want me to show it again?"


async def _dispatch(
    intent: Intent,
    user_message: str,
    *,
    memory: Any = None,
    tz_name: str = "America/Phoenix",
) -> tuple[str, bool, list[str] | None]:
    """Call HCP, format reply. Returns (reply_text, use_markdown, entity_ids or None)."""
    if intent.name == INTENT_HELP:
        return format_help_message(), True, None

    # ---- Confirm: execute pending_action; never route to help/unknown ----
    if intent.name == INTENT_CONFIRM:
        pending = (intent.raw_slots or {}).get("pending_action") if intent.raw_slots else None
        if memory:
            pending = pending or (memory.pending_action if hasattr(memory, "pending_action") else None)
        if not pending:
            return "I'm not sure what to do. Try asking for jobs, estimates, or help.", True, None
        if memory:
            memory.clear_pending_action()
        synthetic = _intent_from_pending_action(pending)
        if synthetic.name == INTENT_UNKNOWN:
            return "I'm not sure what to do. Try asking for jobs, estimates, or help.", True, None
        return await _dispatch(synthetic, user_message, memory=memory, tz_name=tz_name)

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
            return hint, True, None
        return format_unknown_capabilities(with_buttons_hint=False), True, None

    # ---- aggregation unsupported: set pending_action so "yes please" lists jobs ----
    if intent.name == INTENT_AGGREGATION_UNSUPPORTED:
        f = intent.filters
        date_label = (f.date_label or "that period").strip() or "that period"
        start_d = getattr(f, "start_date", None)
        end_d = getattr(f, "end_date", None)
        reply = format_aggregation_unsupported(date_label, start_date=start_d, end_date=end_d)
        if memory and hasattr(memory, "set_pending_action"):
            memory.set_pending_action(_pending_action_for_aggregation(f))
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
        record_jobs_list(len(jobs_list))
        ids = extract_job_ids_from_list(data)
        reply = format_jobs_list_by_day(data, date_label, include_suggestions=True, tz_name=tz_name)
        return reply, True, ids

    # ---- job.get (typed anchor: require anchor.type == "job" when entity from context) ----
    if intent.name == INTENT_JOB_GET and intent.entity_id:
        anchor = memory.get_anchor() if memory else None
        if anchor and intent.entity_id in (anchor.get("ids") or []) and anchor.get("type") != "job":
            return _anchor_type_mismatch_message("job"), True, None
        data = await hcp_jobs.get_job(intent.entity_id)
        if getattr(intent, "focus", None) == "money":
            return responses.format_job_total_only(data), True, None
        return responses.format_job_detail(data, tz_name=tz_name), True, None

    # ---- job.time (typed: only when anchor is job) ----
    if intent.name == INTENT_JOB_TIME and intent.entity_id:
        anchor = memory.get_anchor() if memory else None
        if anchor and intent.entity_id in (anchor.get("ids") or []) and anchor.get("type") != "job":
            return _anchor_type_mismatch_message("job"), True, None
        data = await hcp_jobs.get_job(intent.entity_id)
        return responses.format_job_time_only(data, tz_name=tz_name), True, None

    # ---- estimates.list; return entity_ids for anchor ----
    if intent.name == INTENT_ESTIMATES_LIST:
        status_filter = intent.filters.status if intent.filters else None
        data = await hcp_estimates.list_estimates(status=status_filter)
        ids = extract_entity_ids_from_list(data)
        estimates_list = _list_from_response(data)
        record_estimates_list(len(estimates_list))
        list_label = None
        if status_filter == "unscheduled":
            list_label = "unscheduled estimates"
        elif status_filter == "open":
            list_label = "open estimates"
        return responses.format_estimates_list(data, list_label=list_label), True, ids

    # ---- estimate.get (typed anchor: require anchor.type == "estimate") ----
    if intent.name == INTENT_ESTIMATE_GET and intent.entity_id:
        anchor = memory.get_anchor() if memory else None
        if anchor and intent.entity_id in (anchor.get("ids") or []) and anchor.get("type") != "estimate":
            return "I lost track of the estimate. Want me to show the list again?", True, None
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

    # ---- customers.search (list); return entity_ids for anchor ----
    if intent.name == INTENT_CUSTOMERS_SEARCH:
        data = await hcp_customers.list_customers()
        ids = extract_entity_ids_from_list(data)
        return responses.format_customers_list(data), True, ids

    # ---- customer.get (typed anchor: require anchor.type == "customer") ----
    if intent.name == INTENT_CUSTOMER_GET and intent.entity_id:
        anchor = memory.get_anchor() if memory else None
        if anchor and intent.entity_id in (anchor.get("ids") or []) and anchor.get("type") != "customer":
            return "I lost track of the customer. Want me to show the list again?", True, None
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
