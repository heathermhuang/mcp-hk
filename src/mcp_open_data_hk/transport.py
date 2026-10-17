"""Reviewed public transport request contracts and semantic/freshness validation.

Source records retain operator fields. Only MTR's nested platform/stop wrappers are
flattened, adding the wrapper identity to each record. No caller-supplied URL.
"""

import json
import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from urllib.parse import quote, urlsplit

from .contracts import DomainError

REVISION = "transport-1"
HKT = timezone(timedelta(hours=8))
DATASETS = (
    "mtr-data2-nexttrain-data",
    "mtr-lrnt_data-light-rail-nexttrain-data",
    "mtr-mtr_bus-mtr-bus-eta-data",
    "hk-td-tis_21-etakmb",
    "ctb-eta-transport-realtime-eta",
    "nlb-bus-nlb-bus-service-v2",
    "nlb-bus-nlb-bus-service-v1",
    "hk-td-sm_7-real-time-arrival-data-of-gmb",
    "sunferry-eta-eta",
    "ff-fortune-schedule2",
    "ff-watertaxi-schedule2",
    "hkkf-hkkfdata-hkkf-eta-data",
)


@dataclass
class Profile:
    operator: str
    mode: str
    kind: str
    template: str
    required: list[str] = field(default_factory=list)
    defaults: dict = field(default_factory=dict)
    method: str = "GET"
    ttl: int = 20
    max_age: int = 150

    @property
    def arrivals(self):
        return self.kind in {"mtr", "lrt", "mtrbus", "eta", "gmb", "nlb", "ferry"}

    def describe(self):
        return dict(
            operator=self.operator,
            mode=self.mode,
            operation="arrivals" if self.arrivals else "reference",
            requiredParameters=self.required,
            optionalParameters=self.defaults,
            cacheTTLSeconds=self.ttl,
            maxSourceAgeSeconds=self.max_age,
            validationScope="last_selected_route_or_stop",
            policyVersion=REVISION,
        )


def profile(resource):
    if resource.get("datasetId") not in DATASETS:
        return None
    url = resource["url"]
    host = urlsplit(url).hostname
    path = urlsplit(url).path
    p = None
    if host == "rt.data.gov.hk" and path.endswith("/mtr/getSchedule.php"):
        p = Profile(
            "MTR",
            "rail",
            "mtr",
            "https://rt.data.gov.hk/v1/transport/mtr/getSchedule.php?line={line}&sta={sta}&lang={lang}",
            ["line", "sta"],
            {"lang": "en"},
            ttl=10,
            max_age=60,
        )
    elif host == "rt.data.gov.hk" and "/mtr/lrt/" in path:
        p = Profile(
            "MTR Light Rail",
            "rail",
            "lrt",
            "https://rt.data.gov.hk/v1/transport/mtr/lrt/getSchedule?station_id={station_id}",
            ["station_id"],
            ttl=10,
            max_age=60,
        )
    elif host == "rt.data.gov.hk" and "/mtr/bus/" in path:
        p = Profile(
            "MTR Bus",
            "bus",
            "mtrbus",
            "https://rt.data.gov.hk/v1/transport/mtr/bus/getSchedule",
            ["routeName"],
            {"language": "en"},
            method="POST",
            max_age=150,
        )
    elif host == "rt.data.gov.hk" and ("/citybus-nwfb/" in path or "/citybus/" in path):
        op = path.split("/transport/", 1)[1].split("/")[1]
        tail, names = {
            "eta": ("eta/CTB/{stop_id}/{route}", ["stop_id", "route"]),
            "route-stop": (
                "route-stop/CTB/{route}/{direction}",
                ["route", "direction"],
            ),
            "stop": ("stop/{stop_id}", ["stop_id"]),
            "route": ("route/CTB", []),
            "company": ("company/CTB", []),
        }.get(op, ("", []))
        if tail:
            p = Profile(
                "Citybus",
                "bus",
                "eta" if op == "eta" else "reference",
                "https://rt.data.gov.hk/v2/transport/citybus/" + tail,
                names,
            )
    elif host == "data.etabus.gov.hk" and "/transport/kmb/" in path:
        arrival = any("/" + op + "/" in path for op in ["eta", "stop-eta", "route-eta"])
        p = Profile("KMB/LWB", "bus", "eta" if arrival else "reference", url)
    elif host == "data.etagmb.gov.hk":
        p = Profile(
            "Green minibuses", "minibus", "gmb" if "/eta/" in path else "reference", url
        )
    elif host == "rt.data.gov.hk" and "/transport/nlb/" in path:
        p = Profile(
            "New Lantao Bus",
            "bus",
            "nlb" if "estimatedArrivals" in url else "reference",
            url,
        )
    elif host == "www.sunferry.com.hk" and path.startswith("/eta/"):
        p = Profile("Sun Ferry", "ferry", "ferry", url)
    elif host == "www.hongkongwatertaxi.com.hk" and path.startswith("/eta/"):
        p = Profile("Fortune Ferry / Water Taxi", "ferry", "ferry", url)
    elif host == "www.hkkfeta.com" and "/opendata/" in path:
        op = path.split("/opendata/", 1)[1].split("/")[0]
        tail, names = {
            "eta": ("eta/{route_id}/{direction}", ["route_id", "direction"]),
            "pier": ("pier/{pier_id}", ["pier_id"]),
            "time_table": (
                "time_table/{route_id}/{direction}",
                ["route_id", "direction"],
            ),
            "fare_table": ("fare_table/{route_id}", ["route_id"]),
            "route": ("route", []),
        }.get(op, ("", []))
        if tail:
            p = Profile(
                "Hong Kong & Kowloon Ferry",
                "ferry",
                "ferry" if op == "eta" else "reference",
                "https://www.hkkfeta.com/opendata/" + tail,
                names,
            )
    if p:
        p.required = p.required or sorted(
            {a or b for a, b in re.findall(r"\{([^{}]+)\}|<([^<>]+)>", p.template)}
        )
        p.required = [k for k in p.required if k not in p.defaults]
        if not p.arrivals:
            p.ttl = 300
    return p


def request(p, parameters):
    args = {**p.defaults, **(parameters or {})}
    if set(args) != set(p.required) | set(p.defaults):
        raise DomainError(
            "PARAMETERS_REQUIRED",
            "Provide source parameters: " + ", ".join(p.required),
            400,
        )
    for key, value in args.items():
        if not isinstance(value, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,40}", value
        ):
            raise DomainError(
                "INVALID_QUERY", "Invalid transport parameter: " + key, 400
            )
    if "lang" in args and args["lang"] not in {"en", "tc"}:
        raise DomainError("INVALID_QUERY", "lang must be en or tc", 400)
    if "language" in args and args["language"] not in {"en", "zh"}:
        raise DomainError("INVALID_QUERY", "language must be en or zh", 400)
    if "region" in args and args["region"] not in {"HKI", "KLN", "NT"}:
        raise DomainError("INVALID_QUERY", "region must be HKI, KLN or NT", 400)
    url = p.template
    for key, value in args.items():
        url = url.replace("{" + key + "}", quote(value, safe="")).replace(
            "<" + key + ">", quote(value, safe="")
        )
    return url, args if p.method == "POST" else None


def timestamp(value):
    if not isinstance(value, str):
        raise DomainError(
            "SOURCE_TIMESTAMP_MISSING",
            "Arrival response has no usable source timestamp",
            502,
        )
    try:
        dt = datetime.fromisoformat(value.replace("/", "-").replace("Z", "+00:00"))
        return (dt if dt.tzinfo else dt.replace(tzinfo=HKT)).timestamp()
    except ValueError:
        raise DomainError(
            "SOURCE_SCHEMA_CHANGED", "Invalid transport source timestamp", 502
        ) from None


def validate(body, p, parameters, headers, now=None):
    """Reject provider errors and old payloads before the generic reader accepts them."""
    now = time.time() if now is None else now
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        raise DomainError(
            "SOURCE_RESPONSE_ERROR", "Transport source did not return JSON", 502
        ) from None
    if (
        not isinstance(data, dict)
        or data.get("error")
        or data.get("error_message")
        or (
            p.kind != "mtrbus"
            and "status" in data
            and str(data["status"]) not in {"1", "200"}
        )
    ):

        raise DomainError(
            "SOURCE_RESPONSE_ERROR", "Transport source returned an error response", 502
        )
    extra = {
        "transport": p.describe(),
        "sourceContentHash": hashlib.sha256(body).hexdigest(),
    }
    if p.kind in {"mtr", "lrt"}:
        if str(data.get("status")) != "1":
            raise DomainError(
                "SOURCE_RESPONSE_ERROR",
                str(data.get("message") or "Transport service unavailable")[:200],
                502,
            )
    if p.kind == "mtr":
        station = (data.get("data") or {}).get(
            parameters["line"] + "-" + parameters["sta"]
        )
        if not isinstance(station, dict):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "Missing selected MTR station", 502
            )
        rows = []
        for direction in ["UP", "DOWN"]:
            trains = station.get(direction, [])
            if not isinstance(trains, list) or any(
                not isinstance(t, dict) or "time" not in t for t in trains
            ):
                raise DomainError("SOURCE_SCHEMA_CHANGED", "Invalid MTR arrivals", 502)
            rows.extend(
                dict(
                    t,
                    line=parameters["line"],
                    station=parameters["sta"],
                    direction=direction,
                )
                for t in trains
            )
        generated = data.get("curr_time") or station.get("curr_time")
        extra["serviceContext"] = {k: v for k, v in data.items() if k != "data"}
    elif p.kind == "lrt":
        platforms = data.get("platform_list")
        if not isinstance(platforms, list):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "Missing Light Rail platforms", 502
            )
        rows = []
        for platform in platforms:
            trains = platform.get("route_list", [])
            if not isinstance(trains, list) or any(
                not isinstance(t, dict) or "time_en" not in t for t in trains
            ):
                raise DomainError(
                    "SOURCE_SCHEMA_CHANGED", "Invalid Light Rail arrivals", 502
                )
            rows.extend(
                dict(
                    t,
                    platform_id=platform["platform_id"],
                    station_id=parameters["station_id"],
                )
                for t in trains
            )
        generated = data.get("system_time")
    elif p.kind == "mtrbus":
        stops = data.get("busStop")
        if (
            not isinstance(stops, list)
            or not stops
            or data.get("routeName") != parameters["routeName"]
        ):
            raise DomainError(
                "SOURCE_RESPONSE_ERROR", "MTR Bus returned no valid selected route", 502
            )
        rows = []
        for stop in stops:
            buses = stop.get("bus", [])
            if not isinstance(buses, list) or any(
                not isinstance(b, dict) or "isScheduled" not in b for b in buses
            ):
                raise DomainError(
                    "SOURCE_SCHEMA_CHANGED", "Invalid MTR Bus arrivals", 502
                )
            rows.extend(
                dict(
                    b,
                    busStopId=stop["busStopId"],
                    isSuspended=stop.get("isSuspended"),
                    routeName=parameters["routeName"],
                )
                for b in buses
            )
        generated = data.get("routeStatusTime")
        if str(data.get("status")) != "1":
            extra["transport"]["advisories"] = [
                str(
                    data.get("footerRemarks")
                    or "MTR Bus reports an advisory; check service status."
                )[:1000]
            ]
        extra["serviceContext"] = {k: v for k, v in data.items() if k != "busStop"}
    elif p.kind == "nlb":
        rows = data.get("estimatedArrivals")
        if not isinstance(rows, list) or any(
            not isinstance(r, dict) or "estimatedArrivalTime" not in r for r in rows
        ):
            raise DomainError(
                "SOURCE_RESPONSE_ERROR", "NLB returned no arrival list", 502
            )
        generated = min((r.get("generateTime", "") for r in rows), default=None)
        # Empty NLB response lacks a source timestamp: report unavailable, not live zero.
    elif p.arrivals:
        rows = data.get("data")
        if p.kind == "gmb":
            groups = rows if isinstance(rows, list) else [rows]
            rows = []
            for group in groups:
                if not isinstance(group, dict) or not isinstance(
                    group.get("eta"), list
                ):
                    raise DomainError(
                        "SOURCE_RESPONSE_ERROR",
                        "Invalid green minibus arrival feed",
                        502,
                    )
                if group.get("enabled") is False:
                    raise DomainError(
                        "SOURCE_RESPONSE_ERROR",
                        "Green minibus arrival feed is disabled",
                        502,
                    )
                context = {k: v for k, v in group.items() if k != "eta"}
                rows.extend(dict(r, **context) for r in group["eta"])
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise DomainError("SOURCE_SCHEMA_CHANGED", "Invalid arrival list", 502)
        required = {"eta"} if p.kind in {"eta", "ferry"} else {"timestamp", "diff"}
        if any(
            not required.issubset(r) and not (p.kind == "ferry" and "ETA" in r)
            for r in rows
        ):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "Arrival records are missing time fields", 502
            )
        generated = data.get("generated_timestamp")
    else:
        # Reference endpoints are not advertised as real-time arrivals.
        if str(data.get("status", "1")) not in {"1", "200"}:
            raise DomainError(
                "SOURCE_RESPONSE_ERROR",
                "Transport source returned a failure status",
                502,
            )
        if (
            not any(k in data for k in ("data", "routes", "stops"))
            or "error" in str(data.get("type", "")).lower()
        ):
            raise DomainError(
                "SOURCE_RESPONSE_ERROR",
                "Transport reference response has no expected data",
                502,
            )
        return body, extra
    if p.kind == "nlb" and not rows:
        from email.utils import parsedate_to_datetime

        try:
            generated = parsedate_to_datetime(headers["date"]).isoformat()
            extra["emptyResponseTimestampBasis"] = "provider_http_date"
        except (KeyError, ValueError, TypeError):
            raise DomainError(
                "SOURCE_TIMESTAMP_MISSING",
                "Empty NLB response has no provider timestamp",
                502,
            ) from None
    source_time = timestamp(generated)
    if not -30 <= now - source_time <= p.max_age:
        raise DomainError(
            "STALE_TRANSPORT_DATA",
            "Transport source timestamp is outside the freshness window",
            503,
        )
    for row in rows:
        time_key = {
            "mtr": "time",
            "lrt": "time_en",
            "mtrbus": "arrivalTimeInSecond",
            "gmb": "timestamp",
            "nlb": "estimatedArrivalTime",
        }.get(p.kind, "eta" if "eta" in row else "ETA")
        if row.get(time_key) is not None and not isinstance(row[time_key], str):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "Invalid arrival time field", 502
            )
    fresh_rows = [
        r
        for r in rows
        if all(
            -30 <= now - timestamp(r[k]) <= p.max_age
            for k in ["data_timestamp", "date_timestamp"]
            if r.get(k)
        )
    ]
    if rows and not fresh_rows:
        raise DomainError(
            "STALE_TRANSPORT_DATA",
            "All arrival records are older than the freshness window",
            503,
        )
    extra["transport"]["omittedStaleRecords"] = len(rows) - len(fresh_rows)
    rows = fresh_rows
    extra["transport"].update(
        arrivalState="arrivals" if rows else "no_arrivals",
        sourceTimestamp=generated,
        sourceAgeSeconds=max(0, now - source_time),
        freshnessBasis="provider_timestamp",
        freshUntil=source_time + p.max_age,
    )
    extra["sourceContext"] = {
        k: v
        for k, v in data.items()
        if k not in {"data", "platform_list", "busStop", "estimatedArrivals"}
    }
    extra["scope"] = "selected_route_or_stop_arrivals"
    return json.dumps(rows, ensure_ascii=False).encode(), extra
