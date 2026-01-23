from pydantic import BaseModel, Field, field_validator
import re
import logging

logger = logging.getLogger(__name__)


class PostalCode(BaseModel):
    # Postal code as string (supports US, Canada, and other formats)
    code: str = Field(..., description="Postal/ZIP code")

    @field_validator("code", mode="before")
    @classmethod
    def normalize_postal_code(cls, v):
        """Normalize postal code to clean string format."""
        if v is None:
            return None

        # Convert to string
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

    @property
    def display_format(self):
        """Return postal code in a standard display format."""
        if not self.code:
            return None

        # Canadian postal code: A1A 1A1 format
        canada_pattern = r'^[A-Z]\d[A-Z]\d[A-Z]\d$'
        # US ZIP code: 5 digits or 9 digits (ZIP+4)
        us_zip_pattern = r'^\d{5}$'
        us_zip4_pattern = r'^\d{9}$'

        if re.match(canada_pattern, self.code) and len(self.code) == 6:
            return f"{self.code[:3]} {self.code[3:]}"
        elif re.match(us_zip4_pattern, self.code) and len(self.code) == 9:
            return f"{self.code[:5]}-{self.code[5:]}"
        else:
            return self.code

    @property
    def country_format(self):
        """Detect the country format of the postal code."""
        if not self.code:
            return None

        canada_pattern = r'^[A-Z]\d[A-Z]\d[A-Z]\d$'
        us_zip_pattern = r'^\d{5}$'
        us_zip4_pattern = r'^\d{9}$'

        if re.match(canada_pattern, self.code):
            return "CA"
        elif re.match(us_zip_pattern, self.code) or re.match(us_zip4_pattern, self.code):
            return "US"
        elif self.code.isdigit():
            return "US_NUMERIC"
        else:
            return "UNKNOWN"

    def __hash__(self):
        return hash(self.code)

    def __eq__(self, other):
        if isinstance(other, PostalCode):
            return self.code == other.code
        return False