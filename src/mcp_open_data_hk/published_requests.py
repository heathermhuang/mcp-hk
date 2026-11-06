"""Explicit request bindings from independently checked publisher specifications."""

import math

from .contracts import DomainError
from . import geodetic_requests, hydro_requests

SPEC_PREFIX = "https://portal.csdi.gov.hk/csdi-webpage/apidoc/"
LOCATION_SEARCH_SPEC = (
    "https://portal.csdi.gov.hk/csdi-webpage/apidoc/LocationSearchAPI"
)
LOCATION_SEARCH_TEMPLATE = "https://www.map.gov.hk/gs/api/v1.0.0/locationSearch?q={q}"
IDENTIFY_SPEC = SPEC_PREFIX + "IdentifyAPI"
NEARBY_SPEC = SPEC_PREFIX + "SearchNearbyAPI"
NUMBER_SEARCH_SPEC = SPEC_PREFIX + "LPPUNSearchAPI"
LOT_INDEX_SPEC = SPEC_PREFIX + "LotIndexAPI"
REQUESTS = {
    **{page: hydro_requests.TEMPLATE for page in hydro_requests.PAGES},
    **{
        spec: geodetic_requests.SPEC + "/?inSys={inSys}"
        for spec in geodetic_requests.SPECS
    },
    LOCATION_SEARCH_SPEC: LOCATION_SEARCH_TEMPLATE,
    IDENTIFY_SPEC: (
        "https://www.map.gov.hk/gs/api/v1.0.0/identify?x={x}&y={y}&lang={lang}"
    ),
    NEARBY_SPEC: (
        "https://www.map.gov.hk/gs/api/v1.0.0/searchNearby?x={x}&y={y}&lang={lang}"
    ),
    NUMBER_SEARCH_SPEC: (
        "https://mapapi.hkmapservice.gov.hk/gs/api/v1.0.0/lus/{DataType}/"
        "SearchNumber?text={text}"
    ),
    LOT_INDEX_SPEC: (
        "https://mapapi.hkmapservice.gov.hk/gs/api/v1.0.0/iC1000/{LIT}?"
        "bbox={hk80MinX},{hk80MinY},{hk80MaxX},{hk80MaxY},EPSG:2326"
    ),
}
MAP_SPECS = {SPEC_PREFIX + "VectorMapAPI", SPEC_PREFIX + "VectorMapLabelAPI"}


def non_record_interface(url):
    if url.rstrip("/") in MAP_SPECS:
        return {
            "kind": "vector_tiles_and_map_styles",
            "responseFormats": ["PBF vector tiles", "JSON presentation style"],
            "recordQuerySupported": False,
            "sourceSpecificationUrl": url.rstrip("/"),
        }
    return None


def request_template(url):
    return REQUESTS.get(url.rstrip("/"), url)


def bind_request(url, parameters):
    return geodetic_requests.request(url, parameters)


def parameter_choices(url):
    spec = url.rstrip("/")
    if spec in hydro_requests.PAGES:
        return {"mode": ["A"]}
    if spec in geodetic_requests.SPECS:
        return {"inSys": list(geodetic_requests.SYSTEMS)}
    if spec in {IDENTIFY_SPEC, NEARBY_SPEC}:
        return {"lang": ["en", "zh"]}
    if spec == LOT_INDEX_SPEC:
        return {"LIT": ["lot", "LOT", "GLA", "STT"]}
    if spec == NUMBER_SEARCH_SPEC:
        codes = ["LOT", "STT", "GLA", "LPP", "UN", "BUILDINGCSUID", "LOTCSUID", "PRN"]
        return {"DataType": codes + ["lot", "gla"]}
    return {}


def request_requirements(url):
    spec = url.rstrip("/")
    if spec not in REQUESTS:
        return {}
    result = {
        "sourceSpecificationUrl": spec,
        "scope": "explicit_parameter_response_not_full_inventory",
    }
    if spec in hydro_requests.PAGES:
        result.update(
            interface="published_map_prediction_snapshot_not_period_csv",
            timeFormat="YYYYMMDDHHmmss; quarter hour; native timezone unreviewed",
            publishedClientUrl=hydro_requests.CLIENT,
            publisherNoticeUrl=hydro_requests.NOTICE,
            sourceReuseReview=hydro_requests.reuse_hold(spec),
            originalRepresentationEquivalence="unreviewed",
            navigationUse="Not to be used for navigation.",
        )
    if spec in geodetic_requests.SPECS:
        result.update(geodetic_requests.requirements())
    if spec in {IDENTIFY_SPEC, NEARBY_SPEC, LOT_INDEX_SPEC}:
        result.update(inputCoordinateReferenceSystem="HK80", inputCoordinateUnits="m")
    if spec == LOT_INDEX_SPEC:
        result["maximumExtentM"] = {"width": 750, "height": 600}
    if spec == NEARBY_SPEC:
        result["sourceDeclaredSearchDistanceM"] = 1000
    return result


def validate_parameters(url, parameters):
    spec = url.rstrip("/")
    for name, choices in parameter_choices(url).items():
        if parameters[name] not in choices:
            raise DomainError("INVALID_QUERY", "Unsupported published " + name, 400)
    if spec in hydro_requests.PAGES:
        hydro_requests.validate_parameters(parameters)
    names = (
        ["x", "y"]
        if spec in {IDENTIFY_SPEC, NEARBY_SPEC}
        else (
            ["hk80MinX", "hk80MinY", "hk80MaxX", "hk80MaxY"]
            if spec == LOT_INDEX_SPEC
            else []
        )
    )
    coordinates = {}
    for name in names:
        try:
            value = float(parameters[name])
        except ValueError:
            value = math.nan
        if not math.isfinite(value):
            raise DomainError("INVALID_QUERY", "HK80 coordinates must be finite", 400)
        coordinates[name] = value
    if spec == LOT_INDEX_SPEC:
        width = coordinates["hk80MaxX"] - coordinates["hk80MinX"]
        height = coordinates["hk80MaxY"] - coordinates["hk80MinY"]
        if not (0 < width <= 750 and 0 < height <= 600):
            raise DomainError(
                "INVALID_QUERY", "Lot Index extent must be at most 750 m by 600 m", 400
            )


def annotate_response(url, schema, parameters=None):
    if url.rstrip("/") in geodetic_requests.SPECS:
        geodetic_requests.validate_response(schema)
    if request_template(url) != url:
        schema.update(
            scope="parameter_scoped_source_response",
            sourceSpecificationUrl=url.rstrip("/"),
            sourceRowMeaning=(
                "Original records from this explicit published request; not unique "
                "entities or a complete source inventory."
            ),
            coordinateQualification="unreviewed_native_values",
        )
        if url.rstrip("/") in {
            IDENTIFY_SPEC,
            NEARBY_SPEC,
            LOT_INDEX_SPEC,
        }:
            schema["requestCoordinateReferenceSystem"] = "HK80"
        if url.rstrip("/") == NEARBY_SPEC:
            schema["sourceDeclaredSearchDistanceM"] = 1000
        if url.rstrip("/") in hydro_requests.PAGES:
            hydro_requests.annotate(schema, parameters)
