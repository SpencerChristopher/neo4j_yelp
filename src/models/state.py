from pydantic import BaseModel, Field


class State(BaseModel):
    code: str = Field(..., min_length=2, max_length=2, pattern=r"^[A-Z]{2}$",
                      description="Two-letter uppercase state code")

    # Add this method to make State hashable
    def __hash__(self):
        # Hash based on the state code
        return hash(self.code)