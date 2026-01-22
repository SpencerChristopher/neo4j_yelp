from pydantic import BaseModel, Field, model_validator, field_validator, confloat, conint
from typing import Optional, Any


class Location(BaseModel):
    latitude: Optional[confloat(ge=-90, le=90)] = None
    longitude: Optional[confloat(ge=-180, le=180)] = None


class Business(BaseModel):
    # Identity
    business_id: str
    name: str

    # Address (minimum viable location)
    address: Optional[str] = None        ###! Can be removed
    city: Optional[str] = None ### node should have state + (city or post_code)
    state: str
    postal_code: Optional[str] = None  

    # Geospatial observation
    location: Optional[Location] = None

    # Observational metrics (non-identity)
    stars: Optional[confloat(ge=0.0, le=5.0)] = None
    review_count: Optional[conint(ge=0)] = None #must be int
    is_open: Optional[conint(ge=0, le=1)] = None #Review should be boolean 1 or 0

    # -----------------------------
    # Structural validators only
    # -----------------------------

    @model_validator(mode="before")
    @classmethod
    def merge_lat_lon_into_location(cls, data: Any) -> Any:
        """
        Allows CSVs with top-level latitude/longitude
        while keeping a clean internal Location model.
        """
        if not isinstance(data, dict):
            return data

        lat_present = "latitude" in data
        lon_present = "longitude" in data

        lat = data.pop("latitude", None)
        lon = data.pop("longitude", None)

        if lat_present or lon_present:
            loc = data.get("location") or {}
            if isinstance(loc, dict):
                if lat_present:
                    loc["latitude"] = lat
                if lon_present:
                    loc["longitude"] = lon
                data["location"] = loc

        return data

    @model_validator(mode="after")
    def require_minimum_location(self):
        """
        Enforces:
        - state is required
        - at least one of city or postal_code must exist
        ### REQUIRED MINIMUM LOCATION LOCATION MODE (State and city) or postal_code
        """
        if not (self.city or self.postal_code):
            raise ValueError(
                "Business must have at least one of: city or postal_code"
            )
        return self

    @field_validator("city", mode="before")
    @classmethod
    def normalize_city(cls, v):
        return v.title() if isinstance(v, str) else v

    @field_validator("state", mode="before")
    @classmethod
    def normalize_state(cls, v):
        return v.upper() if isinstance(v, str) else v

    @field_validator("postal_code", mode="before")
    @classmethod
    def normalize_postal_code(cls, v):
        return None if v == "" else v