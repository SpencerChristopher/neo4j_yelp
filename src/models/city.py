from pydantic import BaseModel, Field


class City(BaseModel):
    name: str = Field(..., description="City name")
    state_code: str = Field(..., min_length=2, max_length=2, pattern=r"^[A-Z]{2}$",
                            description="Two-letter uppercase state code")

    # Add this method to make City hashable
    def __hash__(self):
        # Hash based on name and state_code combination
        return hash((self.name, self.state_code))