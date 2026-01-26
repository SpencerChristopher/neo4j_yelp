from pydantic import BaseModel, Field, model_validator
from typing import Optional


class Friend(BaseModel):
    user1: str
    user2: str
    # REMOVED: since: Optional[datetime] = None (CSV doesn't have this field)

    @model_validator(mode="after")
    def normalize_and_validate(self):
        # Sort to ensure undirected storage (store once)
        users = sorted([self.user1, self.user2])
        self.user1, self.user2 = users

        # Prevent self-loops
        if self.user1 == self.user2:
            raise ValueError("User cannot be friends with themselves")

        return self

    def __hash__(self):
        """
        Hash based on the canonical sorted user pair for deduplication.
        This relies on the model_validator to ensure user1 < user2.
        """
        return hash((self.user1, self.user2))

    def __eq__(self, other):
        """
        Equality based on the canonical sorted user pair.
        """
        if not isinstance(other, Friend):
            return NotImplemented
        # Rely on the model_validator to ensure user1 < user2 for both self and other
        return self.user1 == other.user1 and self.user2 == other.user2