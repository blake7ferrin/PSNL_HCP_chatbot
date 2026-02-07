"""Telegram message handlers: receive text -> NLU -> HCP API -> format -> reply."""
import os
from typing import Any
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from src.nlu.intents import (
    parse_intent,
    get_help_message,
    INTENT_JOBS_TODAY,
    INTENT_JOBS_BY_DATE,
    INTENT_JOB_DETAIL,
    INTENT_ESTIMATES_LIST,
    INTENT_ESTIMATE_DETAIL,
    INTENT_CUSTOMERS_LIST,
    INTENT_CUSTOMER_DETAIL,
    INTENT_COMPANY_INFO,
    INTENT_EMPLOYEES_LIST,
    INTENT_PRICEBOOK,
    INTENT_SCHEDULE,
    INTENT_STATS,
    INTENT_HELP,
    INTENT_UNKNOWN,
)
from src.hcp import endpoints
from src.hcp.client import HCPClientError
from src.bot import responses


async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start and /help so users get an immediate response."""
    if not update.message:
        return
    user_id = update.effective_user.id if update.effective_user else None
    if not _is_allowed(user_id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    await update.message.reply_text(get_help_message(), parse_mode="Markdown")


async def handle_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with the user's Telegram ID (for allow-list setup)."""
    if not update.message:
        return
    user_id = update.effective_user.id if update.effective_user else None
    if not _is_allowed(user_id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    uid = user_id if user_id is not None else "?"
    await update.message.reply_text(f"Your Telegram user ID: `{uid}`\nAdd this to ALLOWED_TELEGRAM_IDS to grant access.", parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle an incoming text message: parse intent, call HCP, format, send."""
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not _is_allowed(user_id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    text = update.message.text.strip()
    if text.startswith("/"):
        return  # Commands handled by CommandHandler
    result = parse_intent(text)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        reply, use_markdown = await _dispatch(result.intent, result.params, user_message=text)
    except HCPClientError as e:
        reply, use_markdown = responses.format_error(str(e)), True
    except Exception as e:
        import sys
        print(f"Handler error: {e}", file=sys.stderr, flush=True)
        reply, use_markdown = responses.format_error(str(e)), True

    try:
        await update.message.reply_text(reply or "Something went wrong.", parse_mode="Markdown" if use_markdown else None)
    except Exception as e:
        import sys
        print(f"Failed to send reply: {e}", file=sys.stderr, flush=True)
        try:
            await update.message.reply_text("Something went wrong. Check the bot logs.")
        except Exception:
            pass


def _is_allowed(user_id: int | None) -> bool:
    """Access control: if ALLOWED_TELEGRAM_IDS is set, only those Telegram user IDs may use the bot."""
    allowed = os.getenv("ALLOWED_TELEGRAM_IDS", "").strip()
    if not allowed:
        return True
    if user_id is None:
        return False
    ids = [s.strip() for s in allowed.split(",") if s.strip()]
    return str(user_id) in ids


async def _dispatch(intent: str, params: dict, *, user_message: str = "") -> tuple[str, bool]:
    """Call the right HCP endpoints and return (reply_text, use_markdown)."""
    if intent == INTENT_HELP:
        return get_help_message(), True

    if intent == INTENT_STATS:
        from datetime import date, timedelta
        today = date.today().isoformat()
        week_start = date.today() - timedelta(days=date.today().weekday())
        week_end = week_start + timedelta(days=6)
        jobs_today_data = await endpoints.list_jobs(scheduled_start_date=today)
        jobs_today = len(_get_list(jobs_today_data))
        jobs_this_week = await endpoints.count_jobs_in_date_range(week_start.isoformat(), week_end.isoformat())
        estimates_data = await endpoints.list_estimates(per_page=500)
        estimates_count = len(_get_list(estimates_data))
        customers_data = await endpoints.list_customers(per_page=500)
        customers_count = len(_get_list(customers_data))
        counts = {
            "jobs_today": jobs_today,
            "jobs_this_week": jobs_this_week,
            "estimates": estimates_count,
            "customers": customers_count,
        }
        return responses.format_stats(counts), True

    if intent == INTENT_UNKNOWN:
        return (
            "I didn't understand that. "
            "Say \"help\" for a list of questions I can answer.",
            True,
        )

    if intent == INTENT_JOBS_TODAY:
        from datetime import date
        data = await endpoints.list_jobs(scheduled_start_date=date.today().isoformat())
        if _list_from_response(data):
            from src import llm
            if llm.is_available():
                summary = await llm.format_jobs_list(data, "today", user_message)
                if summary:
                    return summary, False
        return responses.format_jobs_list(data, "today"), True

    if intent == INTENT_JOBS_BY_DATE:
        date_str = params.get("date")
        if not date_str:
            from datetime import date
            date_str = date.today().isoformat()
        date_end = params.get("date_end")
        if date_end:
            data = await endpoints.list_jobs_in_date_range(date_str, date_end)
            date_label = f"{date_str} to {date_end}"
        else:
            data = await endpoints.list_jobs(scheduled_start_date=date_str)
            date_label = date_str
        if _list_from_response(data):
            from src import llm
            if llm.is_available():
                summary = await llm.format_jobs_list(data, date_label, user_message)
                if summary:
                    return summary, False
        return responses.format_jobs_list(data, date_label), True

    if intent == INTENT_JOB_DETAIL:
        job_id = params.get("job_id")
        if not job_id:
            return responses.format_error("No job ID provided."), True
        data = await endpoints.get_job(job_id)
        from src import llm
        if llm.is_available():
            summary = await llm.format_response("job_detail", data, user_message=user_message)
            if summary:
                return summary, False
        return responses.format_job_detail(data), True

    if intent == INTENT_ESTIMATES_LIST:
        data = await endpoints.list_estimates()
        return responses.format_estimates_list(data), True

    if intent == INTENT_ESTIMATE_DETAIL:
        estimate_id = params.get("estimate_id")
        if not estimate_id:
            return responses.format_error("No estimate ID provided."), True
        data = await endpoints.get_estimate(estimate_id)
        from src import llm
        if llm.is_available():
            summary = await llm.format_response("estimate_detail", data, user_message=user_message)
            if summary:
                return summary, False
        return responses.format_estimate_detail(data), True

    if intent == INTENT_CUSTOMERS_LIST:
        data = await endpoints.list_customers()
        return responses.format_customers_list(data), True

    if intent == INTENT_CUSTOMER_DETAIL:
        customer_id = params.get("customer_id")
        if not customer_id:
            return responses.format_error("No customer ID provided."), True
        data = await endpoints.get_customer(customer_id)
        from src import llm
        if llm.is_available():
            summary = await llm.format_response("customer_detail", data, user_message=user_message)
            if summary:
                return summary, False
        return responses.format_customer_detail(data), True

    if intent == INTENT_COMPANY_INFO:
        data = await endpoints.get_company()
        return responses.format_company(data), True

    if intent == INTENT_EMPLOYEES_LIST:
        data = await endpoints.list_employees()
        return responses.format_employees_list(data), True

    if intent == INTENT_PRICEBOOK:
        services = await endpoints.list_services()
        materials = await endpoints.list_materials()
        parts = []
        if services and _list_from_response(services):
            parts.append(responses.format_services_list(services))
        if materials and _list_from_response(materials):
            parts.append(responses.format_materials_list(materials))
        if not parts:
            return "Pricebook data is not available or empty.", True
        return "\n\n".join(parts), True

    if intent == INTENT_SCHEDULE:
        from datetime import date, timedelta
        date_str = params.get("date")
        if not date_str:
            date_str = date.today().isoformat()
        date_end = params.get("date_end")
        if date_end:
            # Range: fetch appointments for each day and merge
            start_d = date.fromisoformat(date_str)
            end_d = date.fromisoformat(date_end)
            all_appointments = []
            d = start_d
            while d <= end_d:
                day_data = await endpoints.list_appointments(scheduled_start_date=d.isoformat())
                all_appointments.extend(_get_list(day_data))
                d += timedelta(days=1)
            data = {"appointments": all_appointments} if all_appointments else {}
            date_label = f"{date_str} to {date_end}"
        else:
            data = await endpoints.list_appointments(scheduled_start_date=date_str)
            date_label = date_str
        if data and _list_from_response(data):
            return responses.format_appointments_list(data, date_label), True
        # Fallback: try listing jobs for that date as a proxy for schedule
        if date_end:
            jobs_data = await endpoints.list_jobs_in_date_range(date_str, date_end)
        else:
            jobs_data = await endpoints.list_jobs(scheduled_start_date=date_str)
        return responses.format_jobs_list(jobs_data, date_label), True

    return "I didn't understand that. Say \"help\" for options.", True


def _get_list(data: Any) -> list:
    """Extract list from API response (jobs, appointments, etc.)."""
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("jobs", "estimates", "customers", "pros", "services", "materials", "appointments", "data", "items"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def _list_from_response(data: Any) -> bool:
    """Return True if response has a non-empty list."""
    return len(_get_list(data)) > 0
