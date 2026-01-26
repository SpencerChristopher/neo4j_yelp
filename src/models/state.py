from pydantic import BaseModel, Field, field_validator


class State(BaseModel):
    code: str = Field(..., min_length=2, max_length=2, pattern=r"^[A-Z]{2}$",
                      description="Two-letter uppercase state code")

    @field_validator("code", mode="before")
    @classmethod
    def normalize_state_code(cls, v):
        """Normalize state code to uppercase."""
        if isinstance(v, str):
            return v.strip().upper()
        return v

    # Add this method to make State hashable
    def __hash__(self):
        # Hash based on the state code
        return hash(self.code)
    def __eq__(self, other):
        if isinstance(other, State):
            return self.code == other.code
        return False