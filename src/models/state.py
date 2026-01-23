from pydantic import BaseModel, Field
from typing import Optional

class State(BaseModel):
    code: str = Field(..., min_length=2, max_length=2, pattern=r"^[A-Z]{2}$", description="Two-letter uppercase state code")
