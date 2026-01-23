from pydantic import BaseModel, Field, conint
from typing import Optional

class PostalCode(BaseModel):
    code: conint(ge=501, le=99950) = Field(..., description="5-digit postal code")
