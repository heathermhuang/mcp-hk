"""Explicit request bindings from independently checked publisher specifications."""

LOCATION_SEARCH_SPEC = (
    "https://portal.csdi.gov.hk/csdi-webpage/apidoc/LocationSearchAPI"
)
LOCATION_SEARCH_TEMPLATE = "https://www.map.gov.hk/gs/api/v1.0.0/locationSearch?q={q}"


def request_template(url):
    if url.rstrip("/") == LOCATION_SEARCH_SPEC:
        return LOCATION_SEARCH_TEMPLATE
    return url


def annotate_response(url, schema):
    if request_template(url) != url:
        schema.update(
            scope="parameter_scoped_source_response",
            sourceSpecificationUrl=LOCATION_SEARCH_SPEC,
            sourceRowMeaning=(
                "Original records from this explicit lookup response; not unique "
                "places or a complete location inventory."
            ),
            coordinateQualification="unreviewed_native_values",
        )
