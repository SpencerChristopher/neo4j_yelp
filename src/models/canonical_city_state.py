from pydantic import BaseModel, Field, field_validator


class CanonicalCityState(BaseModel):
    city: str = Field(..., description="Canonical city name")
    state_code: str = Field(
        ...,
        min_length=2,
        max_length=2,
        pattern=r"^[A-Z]{2}$",
        description="Canonical two-letter uppercase state code"
    )

    model_config = {
        "str_strip_whitespace": True,
        "str_min_length": 1
    }

    @field_validator("city", mode="before")
    @classmethod
    def normalize_city(cls, v):
        return v.strip().title() if isinstance(v, str) else v

    @field_validator("state_code", mode="before")
    @classmethod
    def normalize_state(cls, v):
        return v.strip().upper() if isinstance(v, str) else v

    # ADD THIS METHOD to make the model hashable
    def __hash__(self):
        """
        Make CanonicalCityState hashable so it can be used in sets
        and as dictionary keys.

        Hash is based on the combination of city and state_code
        since this uniquely identifies a canonical city-state pair.
        """
        return hash((self.city, self.state_code))

    # Optional but recommended: Also add __eq__ for consistency
    def __eq__(self, other):
        if isinstance(other, CanonicalCityState):
            return (self.city == other.city and
                    self.state_code == other.state_code)
        return False