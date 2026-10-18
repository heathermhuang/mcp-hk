"""Source-review capacity, separate from source cadence and interactive quotas."""

from contextvars import ContextVar

SOURCE_REVIEW = ContextVar("mcp_hk_source_review", default=False)

DAILY_REVIEW_BUDGET = 50_000
BATCH_SIZE = 256
RECOVERY_BATCH_SIZE = 256
RUN_SECONDS = 90
RECOVERY_SECONDS = 90
SCHEDULE_SECONDS = 300
CONCURRENCY = 6
PER_HOST_CONCURRENCY = 2


def capacity(required, budget=DAILY_REVIEW_BUDGET):
    slots = BATCH_SIZE * (86400 // SCHEDULE_SECONDS)
    available = min(budget, slots)
    return {
        "status": "sufficient" if available >= required * 1.2 else "insufficient",
        "requiredReviewsPerDay": round(required, 2),
        "dailyReviewBudget": budget,
        "scheduledReviewSlotsPerDay": slots,
        "headroomRatio": round(available / required, 3) if required else None,
        "minimumHeadroomRatio": 1.2,
        "scheduleIntervalSeconds": SCHEDULE_SECONDS,
        "batchSize": BATCH_SIZE,
        "concurrency": CONCURRENCY,
        "perHostConcurrency": PER_HOST_CONCURRENCY,
        "scope": "Review attempts, not individual HTTP requests. Configured capacity is not observed throughput or proof that all sources are fresh.",
    }
