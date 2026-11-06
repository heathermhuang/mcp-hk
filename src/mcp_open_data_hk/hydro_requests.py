"""The published Hydro map snapshot is distinct from its period CSV download."""

import json
import re
from datetime import datetime

from .contracts import DomainError
from .resource_formats import invalid, no_duplicates

PAGE = "https://current.hydro.gov.hk/main/download.php?lang=tc"
PAGES = {PAGE.replace("lang=tc", "lang=" + lang) for lang in ["tc", "en", "sc"]}
TEMPLATE = (
    "https://current.hydro.gov.hk/data/static_geojson.php?time={time}&mode={mode}"
)
CLIENT = "https://current.hydro.gov.hk/_js/data_download.js"
NOTICE = "https://current.hydro.gov.hk/main/disclaimer.php?lang=tc"
DATASET = "hk-md-hydro-hong-kong-tidal-stream-prediction"
# A reviewed reuse basis must be recorded in code before public record access.
# Request parameters and environment variables cannot grant source permission.
REUSE_AUTHORIZATION = None


def reuse_hold(url, dataset_id=None):
    if (
        url.rstrip("/") not in PAGES and dataset_id != DATASET
    ) or REUSE_AUTHORIZATION is not None:
        return None
    return {
        "state": "pending_source_reuse_review",
        "reason": "source_reuse_review_required",
        "publisherNoticeUrl": NOTICE,
        "catalogueTermsUrl": "https://data.gov.hk/en/terms-and-conditions",
        "noticeSha256": "14a341a8e49c3f24d29431b8de964a399332ec68f54c4351b12991b75f740cc5",
        "noticeReviewedOn": "2026-11-06",
        "publisherCondition": (
            "Noncommercial reproduction requires Marine Department attribution; "
            "commercial use requires prior written authorization."
        ),
        "publicApiReuseBasis": "unverified",
        "networkAccessAssessment": "not_assessed_by_reuse_policy",
    }


def timestamp(value):
    try:
        if not re.fullmatch(r"[0-9]{14}", value):
            raise ValueError()
        result = datetime.strptime(value, "%Y%m%d%H%M%S")
        if result.minute % 15 or result.second:
            raise ValueError()
        return result.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        raise DomainError(
            "INVALID_QUERY", "Hydro time requires YYYYMMDDHHmmss at a quarter hour", 400
        ) from None


def validate_parameters(parameters):
    timestamp(parameters["time"])


def validate_body(body):
    value = json.loads(
        body,
        object_pairs_hook=no_duplicates,
        parse_constant=lambda _: invalid("Nonfinite JSON number"),
    )
    if isinstance(value, dict) and (
        value.get("success") is False or value.get("error")
    ):
        invalid("Hydro source reported a failure", "SOURCE_API_ERROR")
    if (
        not isinstance(value, dict)
        or value.get("type") != "FeatureCollection"
        or not isinstance(value.get("features"), list)
    ):
        invalid("Expected the complete published Hydro map FeatureCollection")
    times = set()
    for feature in value["features"]:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            invalid("Expected original Hydro prediction features")
        properties = feature.get("properties")
        if (
            not isinstance(properties, dict)
            or type(properties.get("point_id")) is not int
            or not all(
                isinstance(properties.get(k), str) for k in ["time", "knot", "deg"]
            )
            or properties.get("mode") != "A"
        ):
            invalid("Hydro prediction properties changed", "SOURCE_SCHEMA_CHANGED")
        times.add(properties["time"])
    if len(times) > 1:
        invalid("Hydro returned mixed prediction timestamps", "SOURCE_SCHEMA_CHANGED")
    return next(iter(times), None)


def annotate(schema, parameters):
    observed = schema.get("observedPredictionTime")
    if observed is not None and observed != timestamp(parameters["time"]):
        invalid(
            "Hydro returned a different prediction timestamp", "SOURCE_SCHEMA_CHANGED"
        )
    schema.update(
        sourceInterface="published_map_prediction_snapshot",
        publishedClientUrl=CLIENT,
        publisherNoticeUrl=NOTICE,
        advertisedCatalogueFormat="CSV",
        originalRepresentationEquivalence="unreviewed",
        navigationUse="Not to be used for navigation, as stated by the publisher.",
        sourceRowMeaning=(
            "Original prediction feature at the caller-selected timestamp and mode; "
            "not an observation, unique facility, period CSV or complete point inventory."
        ),
        predictionTimezoneQualification="unreviewed_native_timestamp",
    )
