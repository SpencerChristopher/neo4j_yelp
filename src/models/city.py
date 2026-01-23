from pydantic import BaseModel, Field
from typing import Optional

class City(BaseModel):
    name: str = Field(..., description="Name of the city")
    state_code: str = Field(..., min_length=2, max_length=2, pattern=r"^[A-Z]{2}$", description="Two-letter uppercase state code")
