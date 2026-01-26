from pydantic import BaseModel, Field, field_validator
import re
import logging

logger = logging.getLogger(__name__)


class PostalCode(BaseModel):
    """Canonical postal code node - unique by normalized code."""

    code: str = Field(
        ...,
        description="Normalized postal/ZIP code (no spaces, uppercase)"
    )

    # --- VALIDATORS ---

    @field_validator("code", mode="before")
    @classmethod
    def normalize_postal_code(cls, v):
        """Normalize postal code - raise error for invalid input."""
        if v is None:
            raise ValueError("Postal code cannot be None")

        # Convert to string
        if isinstance(v, (int, float)):
            v_str = str(int(v))
        else:
            v_str = str(v).strip()

        # Handle empty strings
        if v_str == "":
            raise ValueError("Postal code cannot be empty")

        # Remove all spaces, hyphens, and separators
        v_str = re.sub(r'[\s\-\.]+', '', v_str)

        # Convert to uppercase
        v_str = v_str.upper()

        return v_str

    @field_validator("code", mode="after")
    @classmethod
    def validate_postal_code_format(cls, v):
        """Validate format and log warnings for non-standard codes."""
        if len(v) < 3:
            raise ValueError(f"Postal code too short: '{v}'")
        if len(v) > 12:
            raise ValueError(f"Postal code too long: '{v}'")

        # US ZIP code patterns
        us_zip_pattern = r'^\d{5}$'  # 5 digits
        us_zip4_pattern = r'^\d{9}$'  # 9 digits (ZIP+4 without separator)

        # Canadian postal code pattern (A1A1A1 format after cleaning)
        canada_pattern = r'^[A-Z]\d[A-Z]\d[A-Z]\d$'

        if not (re.match(us_zip_pattern, v) or
                re.match(us_zip4_pattern, v) or
                re.match(canada_pattern, v)):
            # If it's numeric but not standard US format, or alphanumeric not Canada, raise error.
            # This makes the validator stricter than the one in business.py
            raise ValueError(f"Postal code '{v}' does not match standard US (5 or 9 digit) or Canadian (A1A1A1) formats.")

        # Log warnings for non-standard but accepted numeric/alphanumeric codes if desired,
        # but for this model, we are enforcing strict conformity to known patterns.

        return v

    # --- PROPERTIES ---

    @property
    def display_format(self) -> str:
        """Return in standard display format."""
        fmt = self.country_format
        if fmt == "CA":
            return f"{self.code[:3]} {self.code[3:]}"
        elif fmt == "US_ZIP+4":
            return f"{self.code[:5]}-{self.code[5:]}"
        else:
            return self.code

    @property
    def country_format(self) -> str:
        """Detect country/format type."""
        canada_pattern = r'^[A-Z]\d[A-Z]\d[A-Z]\d$'
        us_zip_pattern = r'^\d{5}$'
        us_zip4_pattern = r'^\d{9}$'

        if re.match(canada_pattern, self.code):
            return "CA"
        elif re.match(us_zip_pattern, self.code):
            return "US_ZIP"
        elif re.match(us_zip4_pattern, self.code):
            return "US_ZIP+4"
        elif self.code.isdigit():
            return "NUMERIC"
        elif re.match(r'^[A-Z0-9]+$', self.code):
            return "ALPHANUMERIC"
        else:
            return "UNKNOWN"

    # --- HASH/EQ FOR DEDUPLICATION ---

    def __hash__(self):
        return hash(self.code)

    def __eq__(self, other):
        if isinstance(other, PostalCode):
            return self.code == other.code
        return False

    def __str__(self):
        return f"PostalCode(code={self.code}, format={self.display_format})"