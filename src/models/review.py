from pydantic import BaseModel, Field, field_validator, model_validator, conint
from datetime import datetime
from typing import Optional, Dict, Any
import logging
import re

logger = logging.getLogger(__name__)


class Review(BaseModel):
    """
    Evidence-based review model - represents an observation/claim, not truth.

    Core principle: Reviews are EVIDENCE NODES that connect users to businesses
    via actions, with metadata about the interaction itself.

    From EDA log: review_id, user_id, business_id, stars, useful, funny, cool, date
    From Arrows diagram: Review node with (review_id, date, stars, useful, funny, cool)
    """

    # --- PRIMARY IDENTITY (Required for all reviews) ---
    review_id: str = Field(..., description="Unique review identifier")
    user_id: str = Field(..., description="User who wrote the review")
    business_id: str = Field(..., description="Business being reviewed")

    # --- OBSERVATION METRICS (The "evidence") ---
    stars: conint(ge=1, le=5) = Field(
        ...,
        description="Star rating (1-5) - user's subjective experience"
    )

    date: datetime = Field(
        ...,
        description="When the observation was made - format: '17/10/2012 01:53'"
    )

    # --- SOCIAL VALIDATION METRICS (Community response to evidence) ---
    useful: conint(ge=0) = Field(
        0,
        description="Count of 'useful' votes - community validation of utility"
    )
    funny: conint(ge=0) = Field(
        0,
        description="Count of 'funny' votes - community validation of humor"
    )
    cool: conint(ge=0) = Field(
        0,
        description="Count of 'cool' votes - community validation of style"
    )

    # --- DERIVED/SENTIMENT PROPERTIES (Optional, can be computed later) ---
    sentiment_score: Optional[float] = Field(
        None,
        ge=-1.0, le=1.0,
        description="Computed sentiment score (-1.0 to 1.0)"
    )

    confidence: Optional[float] = Field(
        None,
        ge=0.0, le=1.0,
        description="Confidence in review validity (for analytics)"
    )

    # --- CONFIGURATION ---
    model_config = {
        "extra": "ignore",  # Ignore any additional columns in CSV
        "str_strip_whitespace": True,
        "validate_assignment": True
    }

    # --- VALIDATORS (Evidence Integrity Checks) ---

    @field_validator("date", mode="before")
    @classmethod
    def parse_review_date(cls, v):
        """
        Parse date from '17/10/2012 01:53' format (day/month/year).

        This format is COMMON in international datasets but DIFFERENT from
        US format. We preserve the original interpretation.
        """
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("Review date cannot be empty")

            try:
                # Primary format from EDA: "17/10/2012 01:53"
                return datetime.strptime(v, "%d/%m/%Y %H:%M")
            except ValueError:
                # Try US format as fallback (though not in your data)
                try:
                    return datetime.strptime(v, "%m/%d/%Y %H:%M")
                except ValueError:
                    # Try date only
                    try:
                        return datetime.strptime(v, "%d/%m/%Y")
                    except ValueError:
                        logger.error(f"Unparseable date format: {v}")
                        raise ValueError(f"Date '{v}' doesn't match expected format 'DD/MM/YYYY HH:MM'")
        return v

    @field_validator("review_id", "user_id", "business_id", mode="before")
    @classmethod
    def normalize_ids(cls, v):
        """Ensure IDs are clean strings."""
        if isinstance(v, str):
            return v.strip()
        if v is None:
            raise ValueError("ID cannot be None")
        return str(v)

    @model_validator(mode="after")
    def validate_review_plausibility(self):
        """
        Check for implausible review patterns.

        This is where we encode business rules about what constitutes
        reasonable evidence vs. potential spam/errors.
        """
        # Check for suspicious timing (reviews from future or ancient past)
        current_year = datetime.now().year
        if self.date.year > current_year:
            logger.warning(f"Review {self.review_id} dated in future: {self.date}")

        if self.date.year < 2000:  # Yelp started ~2004
            logger.warning(f"Review {self.review_id} dated before 2000: {self.date}")

        # Check for extreme vote patterns (potential manipulation)
        total_votes = self.useful + self.funny + self.cool
        if total_votes > 1000:  # Arbitrary high threshold
            logger.info(f"Review {self.review_id} has unusually high votes: {total_votes}")

        # Check rating distribution (1-star with high useful votes often indicates issues)
        if self.stars == 1 and self.useful > 50:
            logger.debug(f"Critical review {self.review_id} has {self.useful} useful votes")

        return self

    # --- EVIDENCE ANALYSIS METHODS ---

    @property
    def engagement_score(self) -> float:
        """
        Calculate total engagement score for this piece of evidence.

        Higher scores indicate more community interaction/validation.
        """
        return float(self.useful + self.funny + self.cool)

    @property
    def normalized_engagement(self) -> float:
        """
        Normalized engagement (0-1 scale) using sigmoid-like function.

        Useful for weighting reviews in sentiment analysis.
        """
        raw = self.engagement_score
        # Sigmoid normalization: 1 / (1 + e^(-x/10))
        # This gives ~0.5 at 10 votes, ~0.88 at 30 votes, ~0.98 at 50 votes
        return 1.0 / (1.0 + (2.71828 ** (-raw / 10.0)))

    @property
    def is_highly_engaged(self) -> bool:
        """Flag for reviews with significant community validation."""
        return self.engagement_score >= 10

    @property
    def rating_category(self) -> str:
        """Categorize the star rating for analysis."""
        if self.stars >= 4.5:
            return "excellent"
        elif self.stars >= 4.0:
            return "very_good"
        elif self.stars >= 3.0:
            return "average"
        elif self.stars >= 2.0:
            return "poor"
        else:
            return "very_poor"

    @property
    def date_key(self) -> str:
        """Format date for time-series analysis."""
        return self.date.strftime("%Y-%m")

    # --- EVIDENCE SERIALIZATION ---

    def to_evidence_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary suitable for evidence storage.

        This separates the core evidence (what we store in Neo4j)
        from the relationship information (user_id, business_id).
        """
        return {
            "review_id": self.review_id,
            "stars": self.stars,
            "date": self.date,
            "useful": self.useful,
            "funny": self.funny,
            "cool": self.cool,
            "sentiment_score": self.sentiment_score,
            "confidence": self.confidence,
            "engagement_score": self.engagement_score,
            "rating_category": self.rating_category,
        }

    def to_relationship_info(self) -> Dict[str, str]:
        """
        Extract relationship information for graph building.

        Returns the IDs needed to create:
        - (:User)-[:WROTE]->(:Review)
        - (:Review)-[:OF]->(:Business)
        """
        return {
            "user_id": self.user_id,
            "business_id": self.business_id,
            "review_id": self.review_id
        }

    # --- HASH/EQ FOR DEDUPLICATION ---

    def __hash__(self):
        """Hash based on review_id for deduplication."""
        return hash(self.review_id)

    def __eq__(self, other):
        """Equality based on review_id."""
        if isinstance(other, Review):
            return self.review_id == other.review_id
        return False

    def __str__(self):
        return (
            f"Review({self.review_id[:8]}...: "
            f"User→{self.user_id[:8]}... reviewed Business→{self.business_id[:8]}... "
            f"on {self.date.strftime('%Y-%m-%d')} with {self.stars}★ "
            f"[Useful:{self.useful}, Funny:{self.funny}, Cool:{self.cool}]"
        )