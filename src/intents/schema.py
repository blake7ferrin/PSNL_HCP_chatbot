"""Dataclasses for Intent and filters. Used by the router and handlers."""
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


# Intent names (stable API for handlers)
INTENT_JOBS_LIST = "jobs.list"
INTENT_JOB_GET = "job.get"
INTENT_JOB_TIME = "job.time"
INTENT_ESTIMATES_LIST = "estimates.list"
INTENT_ESTIMATE_GET = "estimate.get"
INTENT_CUSTOMERS_SEARCH = "customers.search"
INTENT_CUSTOMER_GET = "customer.get"
INTENT_PRICEBOOK_SEARCH = "pricebook.search"
INTENT_COMPANY_INFO = "company.info"
INTENT_SCHEDULE = "schedule"  # alias for jobs.list with date
INTENT_STATS = "stats"
INTENT_HELP = "help"
INTENT_UNKNOWN = "unknown"


@dataclass
class IntentFilters:
    """Extracted filters for list/get intents (date range, status, entity refs)."""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None
    # For "the second one" / "job 3 from the list": index into last list (1-based)
    list_index: Optional[int] = None
    # Raw parsed date strings for display (e.g. "next week")
    date_label: Optional[str] = None


@dataclass
class Intent:
    """Result of intent routing: intent name, confidence, and filters."""
    name: str
    filters: IntentFilters = field(default_factory=IntentFilters)
    # Resolved entity id when intent is job.get, estimate.get, customer.get
    entity_id: Optional[str] = None
    confidence: float = 1.0
    # Optional: raw slots from NLU (e.g. "Tuesday") for follow-up resolution
    raw_slots: dict[str, Any] = field(default_factory=dict)

    @property
    def is_list_intent(self) -> bool:
        return self.name in (
            INTENT_JOBS_LIST,
            INTENT_ESTIMATES_LIST,
            INTENT_CUSTOMERS_SEARCH,
        )

    @property
    def is_get_intent(self) -> bool:
        return self.name in (
            INTENT_JOB_GET,
            INTENT_ESTIMATE_GET,
            INTENT_CUSTOMER_GET,
        )
