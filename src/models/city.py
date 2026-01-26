from pydantic import BaseModel, Field, field_validator


class City(BaseModel):
    name: str = Field(..., description="City name")
    state_code: str = Field(..., min_length=2, max_length=2, pattern=r"^[A-Z]{2}$",
                            description="Two-letter uppercase state code")

    @field_validator("name", mode="before")
    @classmethod
    def normalize_city_name(cls, v):
        """Normalize city name to Title Case."""
        if isinstance(v, str):
            return v.strip().title()
        return v

    # Add this method to make City hashable
    def __hash__(self):
        # Hash based on name and state_code combination
        return hash((self.name, self.state_code))

    def __eq__(self, other):
        if isinstance(other, City):
            return (self.name == other.name and
                    self.state_code == other.state_code)
        return False