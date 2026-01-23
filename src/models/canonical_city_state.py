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
