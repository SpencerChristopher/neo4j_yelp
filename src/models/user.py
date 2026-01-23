# Pydantic model for the User node will be defined here.
from pydantic import BaseModel, Field, field_validator, conint, confloat
from datetime import datetime
from typing import Optional


class User(BaseModel):
    # Identity
    user_id: str

    # Profile
    name: Optional[str] = None
    review_count: Optional[conint(ge=0)] = None
    yelping_since: Optional[datetime] = None
    fans: Optional[conint(ge=0)] = None
    average_stars: Optional[confloat(ge=0.0, le=5.0)] = None

    # Compliments (social capital)
    compliment_hot: Optional[conint(ge=0)] = 0
    compliment_more: Optional[conint(ge=0)] = 0
    compliment_profile: Optional[conint(ge=0)] = 0
    compliment_cute: Optional[conint(ge=0)] = 0
    compliment_list: Optional[conint(ge=0)] = 0
    compliment_note: Optional[conint(ge=0)] = 0
    compliment_plain: Optional[conint(ge=0)] = 0
    compliment_cool: Optional[conint(ge=0)] = 0
    compliment_funny: Optional[conint(ge=0)] = 0
    compliment_writer: Optional[conint(ge=0)] = 0
    compliment_photos: Optional[conint(ge=0)] = 0

    model_config = {
        "extra": "ignore",           # drop elite + unnamed cols
        "str_strip_whitespace": True
    }

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, v):
        return v.title() if isinstance(v, str) else v
