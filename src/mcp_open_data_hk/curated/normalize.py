"""Deterministic, source-faithful transformations; no name-based identity matching."""

import datetime as dt
import unicodedata

TRANSFORM = "enigma-hk-v1"
ACCURACY = {
    None: "day",
    1: "year",
    2: "month",
    3: "unknown",
    4: "year_end",
    5: "month_end",
}


def search_key(value):
    return unicodedata.normalize("NFKC", value).casefold().strip()


def bound(raw, accuracy=None):
    """Keep original values, including zero dates; never upgrade imprecise dates."""
    precision = ACCURACY.get(accuracy, "unsupported")
    if raw is None:
        return None, None, "unknown"
    try:
        value = dt.date.fromisoformat(raw)
    except ValueError:
        return raw, None, "invalid"
    return raw, value, precision


def scope(row, listed, licensed, hk=1):
    reasons = []
    if row["Domicile"] == hk:
        reasons.append("hk_domicile")
    if row["orgType"] == 27:
        reasons.append("registered_non_hk")
    if row["PersonID"] in listed:
        reasons.append("hk_listed_issuer")
    if row["PersonID"] in licensed:
        reasons.append("sfc_firm")
    return reasons


def entity(row, kind, reasons):
    source_id = row["PersonID"]
    return (
        source_id,
        kind,
        reasons,
        row.get("Domicile"),
        row.get("orgType"),
        row["Name1"],
        row.get("Name2"),
        row.get("cName"),
        *bound(row.get("incDate"), row.get("incAcc")),
        *bound(row.get("disDate")),
        row.get("disMode"),
        row.get("modified"),
        row.get("incUpd"),
        row.get("SFCupd"),
    )


def identifiers(row, kind):
    source_id = row["PersonID"]
    yield source_id, "webb:person", str(source_id), "PersonID"
    if kind == "organisation" and row.get("incID"):
        # The archive calls this incorporation number. It is not a verified BRN.
        domicile = row.get("Domicile")
        namespace = (
            f"webb:incorporation:{domicile if domicile is not None else 'unknown'}"
        )
        yield source_id, namespace, row["incID"], "incID"
    if row.get("SFCID"):
        yield source_id, "sfc:ce_reference", row["SFCID"], "SFCID"


def names(row, kind):
    source_id = row["PersonID"]
    table = "organisations" if kind == "organisation" else "people"
    # Keep person surname and given names separately in entities. The display
    # string follows the source's surname-first convention without inference.
    display = row["Name1"]
    if kind == "person" and row.get("Name2"):
        display += ", " + row["Name2"]
    for column, language, value in [
        ("Name1", "und-Latn", display),
        ("cName", "zh", row.get("cName")),
    ]:
        if value:
            yield (
                f"{table}:{source_id}:{column}",
                source_id,
                language,
                value,
                search_key(value),
                "archive_name",
                None,
                None,
                "unknown",
                row.get("modified"),
            )


def old_names(row):
    for column, language in [("oldName", "und-Latn"), ("oldcName", "zh")]:
        value = row.get(column)
        if value:
            yield (
                f"namechanges:{row['ID1']}:{column}",
                row["personID"],
                language,
                value,
                search_key(value),
                "former_name",
                *bound(row.get("dateChanged"), row.get("dateAcc")),
                row.get("modified"),
            )


def appointment(row):
    return (
        row["ID1"],
        row["Company"],
        row["Director"],
        row["positionID"],
        *bound(row.get("ApptDate"), row.get("ApptAcc")),
        *bound(row.get("ResDate"), row.get("ResAcc")),
        row.get("JoinedY"),
        row.get("source"),
        row.get("modified"),
    )


def licence(row, relationship=False):
    values = [row["ID"], row["orgID"]]
    values += [row["staffID"], row["role"]] if relationship else [row["ri"]]
    return (
        *values,
        row["actType"],
        *bound(row.get("startDate")),
        *bound(row.get("endDate")),
        row.get("modified"),
    )
