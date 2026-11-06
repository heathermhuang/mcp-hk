"""Exact request contract from Lands Department's transformation API v2 manual."""

import math
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from .contracts import DomainError

SPEC = "https://www.geodetic.gov.hk/transform/v2"
SPECS = {SPEC, "http://www.geodetic.gov.hk/transform/v2"}
MANUAL = SPEC + "/tformAPI_manual.pdf"
SYSTEMS = {
    "wgsgeog": ["lat", "long"],
    "hkgeog": ["lat", "long"],
    "hkgrid": ["e", "n"],
    "utmgrid": ["zone", "e", "n"],
    "utmref": ["zone", "e", "n"],
}
UNITS = ["decdeg", "decmin", "dms"]
COORDINATES = {
    "wgsLat",
    "wgsLong",
    "wgsEllHgt",
    "hkLat",
    "hkLong",
    "hkEllHgt",
    "hkN",
    "hkE",
    "hkpd",
    "utmGridE",
    "utmGridN",
}
REFERENCE_COORDINATES = {"utmRefE", "utmRefN"}


def invalid(message):
    raise DomainError("INVALID_QUERY", message, 400)


def number(value):
    try:
        result = Decimal(value)
    except InvalidOperation:
        invalid("Transformation coordinates must be finite numbers")
    if not result.is_finite():
        invalid("Transformation coordinates must be finite numbers")
    if result.copy_abs() > 10_000_000:
        invalid("Transformation coordinates exceed the published numeric domain")
    return result


def degrees(value, unit):
    value = number(value)
    if unit == "decdeg":
        return value
    whole = int(abs(value))
    minutes = (abs(value) - whole) * 100
    seconds = (minutes - int(minutes)) * 100 if unit == "dms" else Decimal(0)
    if minutes >= 60 or seconds >= 60:
        invalid("Invalid encoded degrees/minutes/seconds")
    minutes = int(minutes) if unit == "dms" else minutes
    result = Decimal(whole) + Decimal(minutes) / 60 + seconds / 3600
    return -result if value < 0 else result


def requirements():
    return {
        "sourceManualUrl": MANUAL,
        "requiredParametersByInputSystem": {
            name: ["inSys", *fields] for name, fields in SYSTEMS.items()
        },
        "optionalParametersByInputSystem": {
            name: ["outSys", "outUnit"]
            + (["h"] if name in {"wgsgeog", "hkgeog", "hkgrid"} else [])
            + (["inUnit"] if name in {"wgsgeog", "hkgeog"} else [])
            for name in SYSTEMS
        },
        "coordinateFormats": ["decDeg", "decMin", "dms"],
        "utmReferenceDigitWidths": [3, 4, 5],
        "utmReferenceLeadingZerosPreserved": True,
        "defaults": "Omitted optional parameters retain publisher defaults",
    }


def request(url, parameters):
    if url.rstrip("/") not in SPECS:
        return None
    if not isinstance(parameters, dict) or "inSys" not in parameters:
        raise DomainError(
            "PARAMETERS_REQUIRED", "Provide inSys and its coordinates", 400
        )
    if any(
        not isinstance(v, str) or not v or len(v) > 200 for v in parameters.values()
    ):
        invalid("Source parameters must be nonempty strings up to 200 characters")
    system = parameters["inSys"].casefold()
    if system not in SYSTEMS:
        invalid("Unsupported transformation input system")
    required = {"inSys", *SYSTEMS[system]}
    optional = set(requirements()["optionalParametersByInputSystem"][system])
    if (
        not required <= parameters.keys()
        or not parameters.keys() <= required | optional
    ):
        raise DomainError(
            "PARAMETERS_REQUIRED",
            "Required parameters: "
            + ", ".join(sorted(required))
            + "; optional parameters: "
            + ", ".join(sorted(optional)),
            400,
        )
    output = parameters.get("outSys", "all").casefold()
    if output not in {*SYSTEMS, "all"} or output == system:
        invalid("Unsupported or identical transformation output system")
    for name in ["inUnit", "outUnit"]:
        if name in parameters and parameters[name].casefold() not in UNITS:
            invalid("Unsupported transformation coordinate format")
    if "h" in parameters and not -1000 <= number(parameters["h"]) <= 10000:
        invalid("Transformation height must be between -1000 and 10000 metres")
    if system in {"wgsgeog", "hkgeog"}:
        unit = parameters.get("inUnit", "decDeg").casefold()
        lat, lon = (degrees(parameters[k], unit) for k in ["lat", "long"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            invalid("Geographical coordinates are out of range")
        if system == "wgsgeog" and not (
            Decimal("22.13") <= lat <= Decimal("22.57")
            and Decimal("113.82") <= lon <= Decimal("114.48")
        ):
            invalid("WGS84 coordinates exceed the publisher's Hong Kong input range")
    elif system == "utmref":
        zone = parameters["zone"].upper()
        if zone not in {
            "49Q-GE",
            "49Q-HE",
            "50Q-JK",
            "50Q-KK",
            "49Q-GQ",
            "49Q-HQ",
            "50Q-JV",
            "50Q-KV",
        }:
            invalid("Unsupported UTM reference zone")
        e, n = parameters["e"], parameters["n"]
        if (
            not re.fullmatch(r"[0-9]{3,5}", e)
            or not re.fullmatch(r"[0-9]{3,5}", n)
            or len(e) != len(n)
        ):
            invalid("UTM reference coordinates require equal widths of 3 to 5 digits")
    else:
        e, n = number(parameters["e"]), number(parameters["n"])
        if system == "hkgrid":
            valid = 799500 <= e <= 867500 and 799000 <= n <= 848000
        else:
            zone = parameters["zone"].upper()
            valid = 2450600 <= n <= 2498000 and (
                zone == "49Q"
                and 791200 <= e <= 810000
                or zone == "50Q"
                and 190000 <= e <= 243000
            )
        if not valid:
            invalid("Grid coordinates exceed the publisher's input range")
    return SPEC + "/?" + urlencode(parameters)


def validate_response(schema):
    context = schema.get("sourceContext")
    if isinstance(context, dict) and "ErrorCode" in context:
        raise DomainError(
            "SOURCE_API_ERROR", "Transformation API returned an error code", 502
        )
    if not isinstance(context, dict) or not (
        COORDINATES | REFERENCE_COORDINATES
    ).intersection(context):
        raise DomainError(
            "SOURCE_SCHEMA_CHANGED", "Expected transformation coordinate object", 422
        )
    for key in COORDINATES.intersection(context):
        value = context[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or isinstance(value, float)
            and not math.isfinite(value)
        ):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "Invalid transformation coordinate value", 422
            )
    for key in REFERENCE_COORDINATES.intersection(context):
        if not isinstance(context[key], str) or not re.fullmatch(
            r"[0-9]+", context[key]
        ):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "Invalid UTM reference coordinate value", 422
            )
