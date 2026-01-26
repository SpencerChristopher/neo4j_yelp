from pydantic import BaseModel, Field, field_validator, model_validator, conint, confloat
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class User(BaseModel):
    """Complete User model matching CSV structure and Arrows diagram."""

    # --- IDENTITY (Required) ---
    user_id: str = Field(..., description="Unique user identifier")

    # --- PROFILE (From Arrows) ---
    name: Optional[str] = Field(None, description="User's display name")
    review_count: Optional[conint(ge=0)] = Field(None, description="Total reviews written")
    yelping_since: Optional[datetime] = Field(None, description="Account creation date")
    fans: Optional[conint(ge=0)] = Field(None, description="Number of fans/followers")
    average_stars: Optional[confloat(ge=1.0, le=5.0)] = Field(
        None, description="Average rating given by user (1.0-5.0)"
    )

    # --- ENGAGEMENT METRICS (From Arrows - CRITICAL for sentiment) ---
    useful: Optional[conint(ge=0)] = Field(
        None, description="Total 'useful' votes received on reviews"
    )
    funny: Optional[conint(ge=0)] = Field(
        None, description="Total 'funny' votes received on reviews"
    )
    cool: Optional[conint(ge=0)] = Field(
        None, description="Total 'cool' votes received on reviews"
    )

    # --- COMPLIMENT METRICS (Social capital - from CSV) ---
    compliment_hot: Optional[conint(ge=0)] = Field(0, description="Hot' compliments received")
    compliment_more: Optional[conint(ge=0)] = Field(0, description="'More' compliments received")
    compliment_profile: Optional[conint(ge=0)] = Field(0, description="Profile compliments")
    compliment_cute: Optional[conint(ge=0)] = Field(0, description="'Cute' compliments")
    compliment_list: Optional[conint(ge=0)] = Field(0, description="List compliments")
    compliment_note: Optional[conint(ge=0)] = Field(0, description="Note compliments")
    compliment_plain: Optional[conint(ge=0)] = Field(0, description="'Plain' compliments")
    compliment_cool: Optional[conint(ge=0)] = Field(0, description="'Cool' compliments")
    compliment_funny: Optional[conint(ge=0)] = Field(0, description="'Funny' compliments")
    compliment_writer: Optional[conint(ge=0)] = Field(0, description="Writer compliments")
    compliment_photos: Optional[conint(ge=0)] = Field(0, description="Photo compliments")

    # --- CONFIG ---
    model_config = {
        "extra": "ignore",  # Ignore 'elite', 'Column1', and unnamed columns
        "str_strip_whitespace": True,
        "validate_assignment": True
    }

    # --- VALIDATORS ---

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, v):
        """Normalize name to Title Case."""
        if isinstance(v, str):
            return v.strip().title()
        return v

    @field_validator("yelping_since", mode="before")
    @classmethod
    def parse_yelping_since(cls, v):
        """Parse date from '26/02/2014 23:24' format."""
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
            try:
                # Handle "26/02/2014 23:24" format
                return datetime.strptime(v, "%d/%m/%Y %H:%M")
            except ValueError as e:
                logger.warning(f"Could not parse yelping_since date: {v} - Error: {e}")
                # Optionally try other formats or return None
                return None
        return v

    @field_validator("average_stars", mode="after")
    @classmethod
    def validate_average_stars_consistency(cls, v, info):
        """Warn if user has reviews but no average_stars, or vice versa."""
        data = info.data
        review_count = data.get("review_count")

        if v is not None and review_count == 0:
            logger.debug(f"User has average_stars {v} but review_count is 0")

        if review_count and review_count > 0 and v is None:
            logger.warning(f"User has {review_count} reviews but no average_stars")

        return v

    @model_validator(mode="after")
    def validate_engagement_metrics(self):
        """Ensure engagement metrics are plausible relative to review_count."""
        if self.review_count is not None and self.review_count == 0:
            # User with no reviews should have minimal engagement
            if self.useful and self.useful > 10:
                logger.debug(f"User with 0 reviews has useful={self.useful}")
            if self.funny and self.funny > 10:
                logger.debug(f"User with 0 reviews has funny={self.funny}")
            if self.cool and self.cool > 10:
                logger.debug(f"User with 0 reviews has cool={self.cool}")

        return self

    # --- HELPER PROPERTIES ---

    @property
    def total_compliments(self) -> int:
        """Calculate total compliments received."""
        return sum([
            self.compliment_hot or 0,
            self.compliment_more or 0,
            self.compliment_profile or 0,
            self.compliment_cute or 0,
            self.compliment_list or 0,
            self.compliment_note or 0,
            self.compliment_plain or 0,
            self.compliment_cool or 0,
            self.compliment_funny or 0,
            self.compliment_writer or 0,
            self.compliment_photos or 0
        ])

    @property
    def engagement_score(self) -> Optional[float]:
        """Calculate normalized engagement score (0-1)."""
        if not self.review_count or self.review_count == 0:
            return None

        total_engagement = (self.useful or 0) + (self.funny or 0) + (self.cool or 0)
        # Normalize by review count (average engagement per review)
        return total_engagement / self.review_count if self.review_count > 0 else 0

    # --- HASH/EQ FOR DEDUPLICATION ---

    def __hash__(self):
        """Make User hashable based on user_id."""
        return hash(self.user_id)

    def __eq__(self, other):
        """Define equality for User objects."""
        if isinstance(other, User):
            return self.user_id == other.user_id
        return False