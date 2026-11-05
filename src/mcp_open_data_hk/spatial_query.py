"""One bounded point implementation with independently reviewed source bindings."""

import math
import re
from collections import Counter

from .contracts import DomainError
from .resource_fields import selected, MISSING
from .services import distance
from .spatial_profiles import profile_for, fingerprint, accepted_binding


def point(profile, row):
    coordinates = profile["coordinates"]
    if coordinates["kind"] == "decimal_text":
        values = [selected(row, coordinates[k]) for k in ("latitude", "longitude")]
        if any(v is MISSING or v is None or v == "" for v in values):
            return None, "missing"
        if any(
            not isinstance(v, str) or not re.fullmatch(r"\d{1,3}\.\d{1,12}", v)
            for v in values
        ):
            return None, "invalid"
        lat, lon = map(float, values)
    else:
        geometry = selected(row, coordinates["field"])
        if geometry is MISSING or geometry is None:
            return None, "missing"
        if not isinstance(geometry, dict) or geometry.get("type") != "Point":
            return None, "geometry_type"
        values = geometry.get("coordinates")
        if (
            not isinstance(values, list)
            or len(values) not in {2, 3}
            or any(type(v) not in {int, float} for v in values)
        ):
            return None, "invalid"
        lon, lat = values[:2]
    if not all(math.isfinite(v) for v in (lat, lon)) or not (
        22 <= lat <= 23 and 113 <= lon <= 115
    ):
        return None, "invalid"
    return (lat, lon), None


def qualify(resource, rows, schema):
    profile = profile_for(resource)
    if not profile:
        return
    binding = {
        "profileId": profile["id"],
        "profileFingerprint": fingerprint(profile),
        "entityKind": profile["entityKind"],
        "state": "available",
        "crs": "EPSG:4326",
        "axisOrder": (
            "longitude_latitude_for_geometry"
            if profile["coordinates"]["kind"] == "geojson_point"
            else "declared_latitude_longitude_fields"
        ),
        "grain": profile["grain"],
        "identity": profile["identity"],
        "evidence": profile["evidence"],
        "coordinateQualification": profile["coordinateQualification"],
        "qualificationDate": profile["qualifiedDate"],
        "observationTime": None,
        "uniqueFacilityCount": None,
    }
    schema["semanticBinding"] = binding

    def hold(reason):
        binding.update(state="held", reason=reason)

    fields = {
        f["name"]: set(f.get("types", [])) - {"null"}
        for f in schema.get("fields", []) + schema.get("queryFields", [])
    }
    if any(
        not fields.get(name) or not fields[name] <= set(kinds)
        for name, kinds in profile["requiredFields"].items()
    ):
        hold("binding_schema_changed")
        return
    if schema.get("format") != profile["format"] or schema.get("scope") not in {
        "complete_file",
        "complete_streamed_file",
    }:
        hold("binding_representation_changed")
        return
    context = schema.get("sourceContext", {})
    if any(context.get(k) != v for k, v in profile.get("sourceContext", {}).items()):
        hold("binding_source_context_changed")
        return
    selection = schema.get("sourceSelection", {})
    if (
        selection.get("sheet")
        or selection.get("layer") is not None
        or selection.get("parameters")
        or selection.get("recordPath") not in {"", "features", None}
    ):
        hold("binding_selection_not_qualified")
        return
    crs = schema.get("sourceCrs") or schema.get("crs") or context.get("crs")
    if (
        crs
        and crs not in ("EPSG:4326", "urn:ogc:def:crs:OGC::CRS84")
        and crs
        != {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC::CRS84"}}
    ):
        hold("binding_crs_changed")
        return
    counts = Counter()
    ids = Counter()
    for row in rows:
        counts["sourceRows"] += 1
        if any(selected(row, k) != v for k, v in profile.get("rowContext", {}).items()):
            hold("binding_row_context_changed")
        coordinates, reason = point(profile, row)
        if reason:
            counts[
                "missingCoordinates" if reason == "missing" else "invalidCoordinates"
            ] += 1
            if reason == "geometry_type":
                hold("binding_geometry_type_changed")
        else:
            counts["validCoordinates"] += 1
            if profile["coordinates"]["kind"] == "decimal_text":
                try:
                    mirror = tuple(
                        float(selected(row, profile["coordinates"][k]))
                        for k in ("mirrorLatitude", "mirrorLongitude")
                    )
                    if any(abs(a - b) > 1e-7 for a, b in zip(coordinates, mirror)):
                        hold("bilingual_coordinate_conflict")
                except (ValueError, TypeError):
                    hold("bilingual_coordinate_conflict")
            else:
                lat, lon = selected(row, "properties.Latitude"), selected(
                    row, "properties.Longitude"
                )
                if (
                    type(lat) in {int, float}
                    and type(lon) in {int, float}
                    and math.isfinite(lat)
                    and math.isfinite(lon)
                    and distance(*coordinates, lat, lon) > 5
                ):
                    counts["geometryPropertyDisagreementsOver5M"] += 1
        identity = selected(row, profile["identity"]["field"])
        valid = (
            type(identity) is int
            if profile["identity"]["kind"] == "integer"
            else isinstance(identity, str)
            and re.fullmatch(profile["identity"]["pattern"], identity) is not None
        )
        if identity is MISSING or identity is None or identity == "":
            counts["missingSourceIdentifiers"] += 1
        elif not valid:
            counts["invalidSourceIdentifiers"] += 1
        else:
            ids[identity] += 1
    binding["coverage"] = {
        **{
            key: counts[key]
            for key in [
                "sourceRows",
                "validCoordinates",
                "missingCoordinates",
                "invalidCoordinates",
                "missingSourceIdentifiers",
                "invalidSourceIdentifiers",
                "geometryPropertyDisagreementsOver5M",
            ]
        },
        "distinctSourceIdentifiers": len(ids),
        "duplicateSourceIdentifierRows": sum(n - 1 for n in ids.values()),
        "scope": "source_records_not_unique_facilities",
    }


class Nearby:
    def __init__(self, resource, schema, query, offset, limit):
        self.profile = profile_for(resource)
        binding = accepted_binding(resource, schema)
        if not self.profile or not binding or binding.get("state") != "available":
            raise DomainError(
                "NEARBY_BINDING_REQUIRED",
                "This exact source selection needs an accepted reviewed point binding",
                422,
            )
        if not isinstance(query, dict) or set(query) != {"lat", "lon", "radiusM"}:
            raise DomainError(
                "INVALID_QUERY", "Nearby requires lat, lon and radiusM", 400
            )
        self.lat, self.lon, self.radius = query["lat"], query["lon"], query["radiusM"]
        if (
            any(
                type(v) not in {int, float} or not math.isfinite(v)
                for v in (self.lat, self.lon, self.radius)
            )
            or not (
                22 <= self.lat <= 23
                and 113 <= self.lon <= 115
                and 1 <= self.radius <= 2000
            )
            or offset + limit > 1000
        ):
            raise DomainError(
                "INVALID_QUERY",
                "Use HK WGS84 coordinates, radius 1..2000 m and the first 1000 ordered matches",
                400,
            )
        self.binding = binding

    def distance(self, row):
        coordinates, reason = point(self.profile, row)
        return distance(self.lat, self.lon, *coordinates) if not reason else None

    def includes(self, row):
        value = self.distance(row)
        return value is not None and value <= self.radius
