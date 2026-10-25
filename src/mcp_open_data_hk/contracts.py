"""Shared HTTP/MCP contracts. Source publication and retrieval dates are distinct."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DomainError(Exception):
    def __init__(
        self, code: str, message: str, status: int = 503, retry_after: int | None = None
    ):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.status = code, message, status
        self.retry_after = retry_after


class Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class Name(Model):
    en: str | None = None
    zhHant: str | None = None


class Address(Model):
    id: str
    name: Name
    address: Name
    districtId: str | None
    latitude: float | None
    longitude: float | None
    score: float | None


class Restaurant(Model):
    id: str = Field(min_length=1)
    name: Name
    address: Name
    districtId: str | None
    licenceType: str
    latitude: float | None
    longitude: float | None
    upstreamUpdatedAt: str | None = None


class DistrictStatistics(Model):
    id: str
    districtId: str
    name: Name
    referencePeriod: int = Field(ge=2000, le=2100)
    population: int = Field(ge=0)
    areaKm2: float = Field(gt=0)
    populationDensity: float = Field(ge=0)
    populationUnit: Literal["persons"] = "persons"
    densityUnit: Literal["persons/km2"] = "persons/km2"


class RestaurantQuery(Model):
    q: str = Field(default="", max_length=200)
    district: str | None = None
    licenceType: str | None = None
    lat: float | None = Field(default=None, ge=22.1, le=22.6)
    lon: float | None = Field(default=None, ge=113.8, le=114.6)
    radiusM: int | None = Field(default=None, ge=50, le=5000)
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=2048)
    includeSummary: bool = False
    requireFresh: bool = False
    lang: Literal["en", "zh-Hant"] = "en"

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon must be supplied together")
        if self.lat is None and self.radiusM is not None:
            raise ValueError("radiusM requires lat and lon")
        return self


class Envelope(Model):
    data: Any
    meta: dict[str, Any]
    provenance: list[dict[str, Any]]
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class PropertySearchQuery(Model):
    q: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=20)
    lang: Literal["en", "zh-Hant"] = "en"

    @model_validator(mode="after")
    def nonblank(self):
        self.q = self.q.strip()
        if not self.q:
            raise ValueError("Provide a building, estate or address")
        return self


class PropertyBuildingQuery(Model):
    buildingId: str = Field(
        min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9:_-]*$"
    )
    lang: Literal["en", "zh-Hant"] = "en"


class PropertyListingsQuery(PropertyBuildingQuery):
    quality: Literal["all", "current"] = "all"


PlateDataset = Literal["all", "pvrm", "tvrm_physical", "tvrm_eauction", "tvrm_legacy"]


class PlateSearchQuery(Model):
    q: str = Field(min_length=1, max_length=16)
    dataset: PlateDataset = "all"
    mode: Literal["exact", "exact_prefix", "contains"] = "exact"
    sort: Literal["amount_desc", "amount_asc", "date_desc", "plate_asc"] = "date_desc"
    page: int = Field(default=1, ge=1, le=100)
    pageSize: int = Field(default=20, ge=1, le=50)


class PlateComparablesQuery(Model):
    q: str = Field(min_length=1, max_length=16)
    page: int = Field(default=1, ge=1, le=100)
    pageSize: int = Field(default=8, ge=1, le=50)


class CompanySearchQuery(Model):
    groupBy: Literal["organisation"] | None = None
    q: str | None = Field(default=None, min_length=2, max_length=200)
    namespace: str | None = Field(default=None, max_length=100)
    value: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=2048)
    view: Literal["archive", "latest_observed"] = "archive"
    requireFresh: bool = False

    @model_validator(mode="after")
    def choose_search(self):
        if self.groupBy and self.limit > 20:
            raise ValueError("Grouped search returns at most 20 organisations")
        if self.q is not None:
            self.q = self.q.strip()
            if len(self.q) < 2 or self.namespace is not None or self.value is not None:
                raise ValueError(
                    "Choose a two-character name prefix or an explicit identifier"
                )
        elif not self.namespace or not self.value:
            raise ValueError("An explicit identifier namespace and value are required")
        return self


class CompanyReadQuery(Model):
    version: str | None = Field(
        default=None, max_length=100, pattern=r"^[A-Za-z0-9._-]+$"
    )
    view: Literal["archive", "latest_observed"] = "archive"
    requireFresh: bool = False


class CompanyHistoryQuery(CompanyReadQuery):
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=2048)
    asOf: str | None = Field(default=None, max_length=10)
