"""Strict offline factual-family contracts; no source route or public mode grant.

A normalized batch cannot establish a real provider layout or coverage. Independent
inventory/capture evidence is required before a source adapter may publish it.
The existing SQLite/R2 scheduler remains the only production racing producer.
"""

from datetime import date
from decimal import Decimal

from .normalize import decimal_text, participant
from .policy import RacingRejected, checksum, utc

DEPENDENCIES = {
    "declarations": [
        "independent race/runner inventory including scratches and withdrawals",
        "declaration capture distinct from results capture",
        "qualified source status dictionary and both language captures",
    ],
    "full_profiles": [
        "complete exact horse/jockey/trainer cohort",
        "career page inventory with source totals and all pages/seasons",
        "dated stable source identities; no reconstructed pre-observation values",
    ],
    "sectionals": [
        "independent race and runner sectional source captures",
        "segment order, distance and timing precision dictionary",
        "complete segment/runner inventory reconciled to declared race distance",
    ],
    "trials": [
        "trial date/session/group inventory and all pages",
        "trial-specific source identity and result semantics",
        "running order distinct from explicitly declared official placing",
    ],
    "jockey_rankings": [
        "exact source period/metric/unit and complete participant inventory",
        "official rank and tie semantics; no rank inferred from result subset",
    ],
    "trainer_rankings": [
        "exact source period/metric/unit and complete participant inventory",
        "official rank and tie semantics; no rank inferred from result subset",
    ],
    "jackpots": [
        "named pool and meeting/race eligibility",
        "source amount/currency and as-at time",
        "carryover versus announced jackpot dictionary",
    ],
    "odds_combinations": [
        "exact named market/selection and combination ordering dictionary",
        "quoted value/unit and suspended/closed semantics",
        "prospective start/cadence/retention/gaps; no historical ticks inferred",
    ],
    "pool_investments": [
        "exact named pool/selection coverage",
        "source investment unit/currency/time",
        "prospective start/cadence/retention/gaps; no historical ticks inferred",
    ],
    "racing_changes": [
        "independent source change identifier and affected race/runner",
        "source event/effective/observed timestamps and correction links",
        "prospective start/cadence/retention/gaps",
    ],
    "intraday_observations": [
        "qualified exact routes and source/output policy",
        "actual start, market, units, timestamps, finite retention and cadence",
        "observed ticks and explicit gaps only; historical source required for past ticks",
    ],
    "narrative_comments": [
        "independent source/output disposition for narrative material",
        "qualified fields and retention/output evidence; no narrative copied under factual-results grant",
    ],
}


def exact_inventory(expected, observed):
    if (
        not isinstance(expected, list)
        or not expected
        or len(expected) > 10000
        or len(set(expected)) != len(expected)
        or len(set(observed)) != len(observed)
        or set(expected) != set(observed)
    ):
        raise RacingRejected("FAMILY_INVENTORY_GAP")
    return checksum(sorted(expected))


def declarations(expected, declared, results, *, declaration_capture, result_capture):
    if (
        declaration_capture == result_capture
        or not declaration_capture
        or not result_capture
    ):
        raise RacingRejected("INDEPENDENT_DECLARATION_CAPTURE_REQUIRED")
    exact_inventory(expected, [r["participantId"] for r in declared])
    outcomes = {r["participantId"]: r for r in results}
    if len(outcomes) != len(results) or set(outcomes) - set(expected):
        raise RacingRejected("DECLARED_RESULT_IDENTITY_MISMATCH")
    gaps, withdrawn, unreported = [], [], []
    for row in declared:
        if row["state"] not in {"declared", "scratched", "withdrawn", "reserve"}:
            raise RacingRejected("DECLARATION_STATUS_UNQUALIFIED")
        outcome = outcomes.get(row["participantId"])
        if row["state"] in {"scratched", "withdrawn"}:
            withdrawn.append(row["participantId"])
            if outcome and outcome["status"] not in {"withdrawn", "not_reported"}:
                raise RacingRejected("WITHDRAWAL_RESULT_CONFLICT")
        elif row["state"] == "declared" and outcome is None:
            gaps.append(row["participantId"])
        if outcome and outcome["status"] == "not_reported":
            unreported.append(row["participantId"])
    return {
        "complete": not gaps and not unreported,
        "missingResultIds": gaps,
        "withdrawnOrScratchedIds": withdrawn,
        "unreportedResultIds": unreported,
        "reserveIds": [r["participantId"] for r in declared if r["state"] == "reserve"],
        "declarationInventorySha256": checksum(sorted(expected)),
    }


def sectionals(rows, *, distance_m, total_seconds=None, precision_seconds="0.01"):
    if type(distance_m) is not int or distance_m <= 0 or not rows:
        raise RacingRejected("SECTIONAL_DISTANCE_REQUIRED")
    if [r["segment"] for r in rows] != list(range(1, len(rows) + 1)):
        raise RacingRejected("SECTIONAL_ORDER_OR_GAP")
    prior, total = 0, Decimal(0)
    for row in rows:
        if (
            row["unit"] != "seconds"
            or type(row["endDistanceM"]) is not int
            or not prior < row["endDistanceM"] <= distance_m
        ):
            raise RacingRejected("SECTIONAL_DISTANCE_OR_UNIT")
        seconds = Decimal(decimal_text(row["seconds"]))
        if seconds <= 0:
            raise RacingRejected("SECTIONAL_TIME_REQUIRED")
        total += seconds
        prior = row["endDistanceM"]
    if prior != distance_m:
        raise RacingRejected("SECTIONAL_DISTANCE_GAP")
    precision = Decimal(decimal_text(precision_seconds))
    if precision <= 0 or precision > 1:
        raise RacingRejected("SECTIONAL_PRECISION_REQUIRED")
    if total_seconds is not None and abs(
        total - Decimal(decimal_text(total_seconds))
    ) > precision * len(rows):
        raise RacingRejected("SECTIONAL_TOTAL_MISMATCH")
    return {
        "segments": len(rows),
        "distanceM": distance_m,
        "sumSeconds": str(total),
        "totalReconciled": total_seconds is not None,
    }


def career(expected, rows, *, kind, source_id, source_total):
    subject = participant(kind, source_id)
    exact_inventory(expected, [r["sourceRaceId"] for r in rows])
    if (
        type(source_total) is not int
        or source_total != len(rows)
        or any(r["participantId"] != subject for r in rows)
    ):
        raise RacingRejected("CAREER_COHORT_OR_TOTAL_GAP")
    return {
        "participantId": subject,
        "races": len(rows),
        "completeWithinDeclaredSourceInventory": True,
        "completeLifetimeHistory": False,
    }


def trial(row):
    if row["kind"] != "barrier_trial" or row["orderMeaning"] not in {
        "running_order",
        "official_placing",
        "not_stated",
    }:
        raise RacingRejected("TRIAL_SEMANTICS_UNQUALIFIED")
    if (
        row["orderMeaning"] != "official_placing"
        and row.get("officialPlacing") is not None
    ):
        raise RacingRejected("TRIAL_PLACING_NOT_DECLARED")
    date.fromisoformat(row["date"])
    return dict(row)


def rankings(expected, rows, *, kind, start, end, metric, unit):
    if (
        kind not in {"jockey", "trainer"}
        or date.fromisoformat(start) > date.fromisoformat(end)
        or not metric
        or not unit
    ):
        raise RacingRejected("RANKING_PERIOD_METRIC_REQUIRED")
    exact_inventory(expected, [r["sourceId"] for r in rows])
    for row in rows:
        participant(kind, row["sourceId"])
        if (
            type(row["rank"]) is not int
            or row["rank"] < 1
            or type(row["tied"]) is not bool
        ):
            raise RacingRejected("RANKING_SOURCE_RANK_REQUIRED")
        decimal_text(row["value"])
    for rank in {r["rank"] for r in rows}:
        group = [r for r in rows if r["rank"] == rank]
        if len(group) > 1 and not all(r["tied"] for r in group):
            raise RacingRejected("RANKING_TIE_UNQUALIFIED")
    return {
        "participants": len(rows),
        "metric": metric,
        "unit": unit,
        "period": [start, end],
        "rankInferred": False,
    }


def jackpot(row):
    if (
        row["kind"] not in {"announced_jackpot", "carryover"}
        or row["currency"] != "HKD"
        or not row["pool"]
    ):
        raise RacingRejected("JACKPOT_KIND_OR_UNIT")
    utc(row["observedAt"])
    return dict(row, amount=decimal_text(row["amount"]), stakeNormalized=False)


def prospective(spec, rows, *, end):
    from .series import series_receipt, observation

    if (
        spec["kind"] not in {"odds", "pool_investments", "changes"}
        or not spec["market"]
        or not spec["unit"]
        or type(spec["retentionSeconds"]) is not int
        or spec["retentionSeconds"] <= 0
    ):
        raise RacingRejected("PROSPECTIVE_SPEC_UNQUALIFIED")
    start = utc(spec["notBefore"])
    finish = utc(end)
    if finish < start:
        raise RacingRejected("PROSPECTIVE_WINDOW_REJECTED")
    for row in rows:
        normalized = observation(row)
        if (
            row["kind"] != spec["kind"]
            or row["market"] != spec["market"]
            or row["rawUnit"] != spec["unit"]
            or not start <= utc(row["observedAt"]) <= finish
            or (finish - utc(row["observedAt"])).total_seconds()
            > spec["retentionSeconds"]
        ):
            raise RacingRejected("PROSPECTIVE_SCOPE_MISMATCH")
        if row["kind"] == "pool_investments" and row.get("currency") != "HKD":
            raise RacingRejected("POOL_CURRENCY_REQUIRED")
        if normalized.get("sourceAt") and utc(normalized["sourceAt"]) < start:
            raise RacingRejected("PROSPECTIVE_HISTORICAL_TICK_REJECTED")
    receipt = series_receipt(rows, spec["cadenceSeconds"], end=end)
    return dict(receipt, specification=spec, historicalTicksInferred=False)
