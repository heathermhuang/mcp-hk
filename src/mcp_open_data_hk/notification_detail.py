"""The exact published notification-detail response; no active-alert semantics."""

import hashlib
import json
import re

from .contracts import DomainError
from .resource_formats import invalid, no_duplicates, parse, text

DATASET = "hk-dpo-mobileapps-govhk-notifications"
URL = "https://ogcmn.one.gov.hk/ogcmn/service/noti/detail/{notification-id}"
DICTIONARY = (
    "https://www.gov.hk/en/about/govdirectory/mobileapps/psi/"
    "iamsmart_newsandalerts/datasets/iAMSmartNews%26AlertsDataSpec.pdf"
)
REVISION = "notification-detail-1"
TEXT_FIELDS = (
    "subject_en",
    "subject_tc",
    "subject_sc",
    "msg_en",
    "msg_tc",
    "msg_sc",
    "source_id",
)
FIELDS = {"id", "schedule_ts", "exp_ts", *TEXT_FIELDS}


def profile(resource):
    return (
        resource.get("datasetId") == DATASET
        and resource.get("url") == URL
        and resource.get("format") == "JSON"
    )


def read(body, record_path="", sheet="", layer=None):
    if record_path or sheet or layer is not None:
        raise DomainError(
            "INVALID_QUERY",
            "Select the complete notification detail by its native ID",
            400,
        )
    value, _ = text(body)
    match = re.fullmatch(r"\s*NotiDetail\((.*)\)\s*;\s*", value, re.DOTALL)
    if not match:
        invalid("Expected the complete published NotiDetail JSONP wrapper")
    payload = json.loads(
        match[1],
        object_pairs_hook=no_duplicates,
        parse_constant=lambda _: invalid("Nonfinite notification value"),
    )
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        invalid("Notification detail fields changed or an error response was returned")
    if type(payload["id"]) not in {int, str} or str(payload["id"]) == "":
        invalid("Expected a native notification identifier")
    if any(not isinstance(payload[name], str) for name in TEXT_FIELDS):
        invalid(
            "Expected native notification text, including unmodified message strings"
        )
    if any(type(payload[name]) is not int for name in ["schedule_ts", "exp_ts"]):
        invalid("Expected native integer notification timestamps")
    rows, schema = parse(match[1].encode(), "JSON")
    if rows != [payload]:
        invalid("Notification detail extraction changed its complete source object")
    schema.update(
        sourceContract={"id": REVISION, "dictionaryUrl": DICTIONARY},
        observedSerialization="fixed_NotiDetail_jsonp_wrapper",
        sourceNotificationId=payload["id"],
        sourceContentHash=hashlib.sha256(body).hexdigest(),
        sourceResponseBytes=len(body),
        sourceFramingFullyConsumed=True,
    )
    return rows, schema


def requirements():
    return {
        "sourceSpecificationUrl": DICTIONARY,
        "scope": "single_native_notification_detail",
        "sourceIdBasis": "Use an original id from the published notification list.",
        "sourceRowMeaning": "Original notification detail; no active-alert or safety qualification.",
        "timestampUnitQualification": "unreviewed_list_detail_dictionary_unit_difference",
        "messageContentQualification": "native_strings_not_rendered_or_followed",
    }


def annotate(schema, parameters):
    if str(schema.get("sourceNotificationId", "")) != (parameters or {}).get(
        "notification-id"
    ):
        invalid("Notification detail identifier differs from the requested native ID")
    schema.update(requirements())
