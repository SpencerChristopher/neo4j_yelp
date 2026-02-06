from pydantic import BaseModel, Field, model_validator, field_validator, confloat, conint
from typing import Optional, Any
import re
import logging

logger = logging.getLogger(__name__)


class Location(BaseModel):
    latitude: Optional[confloat(ge=-90, le=90)] = None
    longitude: Optional[confloat(ge=-180, le=180)] = None

    def __hash__(self):
        return hash((self.latitude, self.longitude))


class Business(BaseModel):
    # Pydantic model configuration
    model_config = {
        "extra": "ignore"  # Ignore extra fields not defined in the model
    }

    # Identity
    business_id: str
    name: str

    # Address (minimum viable location)
    city: Optional[str] = None
    state: str = Field(..., min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")

    # CHANGED: Postal code is now a string to handle both US and Canadian formats
    postal_code: Optional[str] = None

    # Geospatial observation
    location: Optional[Location] = None

    # Observational metrics (non-identity)
    stars: Optional[confloat(ge=0.0, le=5.0)] = None
    review_count: Optional[conint(ge=0)] = None  # must be int
    is_open: Optional[conint(ge=0, le=1)] = None  # Review should be boolean 1 or 0

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
        Enforces that a business has a valid minimum location, which consists of:
        - A mandatory 'state'.
        - At least one of 'city' or 'postal_code' that is not just whitespace.
        """
        has_city = self.city is not None and len(self.city.strip()) > 0
        has_postal = (
                self.postal_code is not None and len(self.postal_code.strip()) > 0
        )
        if not (has_city or has_postal):
            raise ValueError(
                "A Business must have a 'state' and at least one of 'city' or 'postal_code' with a non-empty value."
            )
        return self

    @field_validator("city", mode="before")
    @classmethod
    def normalize_city(cls, v):
        """Normalize city name to Title Case."""
        if isinstance(v, str):
            return v.strip().title()
        return v

    @field_validator("state", mode="before")
    @classmethod
    def normalize_state(cls, v):
        """Normalize state/province code to uppercase."""
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @field_validator("postal_code", mode="before")
    @classmethod
    def normalize_postal_code(cls, v):
        """
        Normalize postal codes to a clean string format.
        - Removes all spaces and hyphens
        - Converts to uppercase
        - Handles both US (12345) and Canadian (A1A1A1) formats
        """
        if v is None:
            return None

        # Convert to string and clean up
        if isinstance(v, (int, float)):
            v_str = str(int(v))  # Handle integers
        else:
            v_str = str(v).strip()

        # Handle empty strings
        if v_str == "":
            return None

        # Remove all spaces, hyphens, and other separators
        v_str = re.sub(r'[\s\-]+', '', v_str)

        # Convert to uppercase
        v_str = v_str.upper()

        return v_str

    @field_validator("postal_code", mode="after")
    @classmethod
    def validate_postal_code_format(cls, v):
        """
        Validate and optionally log postal code format.
        Accepts both US and Canadian formats.
        """
        if v is None:
            return None

        # US ZIP code patterns
        us_zip_pattern = r'^\d{5}$'  # 5 digits
        us_zip4_pattern = r'^\d{9}$'  # 9 digits (ZIP+4 without separator)

        # Canadian postal code pattern (A1A1A1 format after cleaning)
        canada_pattern = r'^[A-Z]\d[A-Z]\d[A-Z]\d$'

        is_valid = False
        format_type = "unknown"

        if re.match(us_zip_pattern, v):
            is_valid = True
            format_type = "US_ZIP"
        elif re.match(us_zip4_pattern, v):
            is_valid = True
            format_type = "US_ZIP4"
        elif re.match(canada_pattern, v):
            is_valid = True
            format_type = "CANADA_POSTAL"
        else:
            format_type = "NONSTANDARD_INVALID" # Explicitly mark as invalid

        # Log the format detection (optional)


        if not is_valid:
            logger.warning(f"Invalid postal code format: '{v}'. Setting to None.")
            return None

        return v

    @property
    def cleaned_postal_code(self):
        """Return the postal code in cleaned format (no spaces)."""
        return self.postal_code

    @property
    def display_postal_code(self):
        """Return postal code in a standard display format."""
        if not self.postal_code:
            return None

        # Canadian format: A1A 1A1
        canada_pattern = r'^[A-Z]\d[A-Z]\d[A-Z]\d$'
        # US ZIP: 12345 or 12345-6789
        us_zip_pattern = r'^\d{5}$'
        us_zip4_pattern = r'^\d{9}$'

        if re.match(canada_pattern, self.postal_code):
            # Format as A1A 1A1
            return f"{self.postal_code[:3]} {self.postal_code[3:]}"
        elif re.match(us_zip_pattern, self.postal_code):
            # 5-digit US ZIP
            return self.postal_code
        elif re.match(us_zip4_pattern, self.postal_code):
            # 9-digit US ZIP+4: 12345-6789
            return f"{self.postal_code[:5]}-{self.postal_code[5:]}"
        else:
            return self.postal_code

    def __hash__(self):
        """Make Business hashable based on business_id."""
        return hash(self.business_id)

    def __eq__(self, other):
        """Define equality for Business objects."""
        if isinstance(other, Business):
            return self.business_id == other.business_id
        return False