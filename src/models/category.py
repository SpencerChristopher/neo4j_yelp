from pydantic import BaseModel, Field, field_validator
from typing import Optional
import re # Added import for regex operations


class Category(BaseModel):
    """Canonical category node - unique by name."""
    name: str

    # Optional: Store any metadata about the category itself
    # description: Optional[str] = None

    @field_validator("name", mode="before")
    @classmethod
    def clean_category_name(cls, v):
        """Clean and standardize category names."""
        if not isinstance(v, str):
            return v

        cleaned = v.strip()
        if not cleaned:
            return cleaned

        words = cleaned.split()
        processed_words = []
        for word in words:
            if word.upper() in ["II", "III", "IV", "LLC", "USA", "ATV", "DVD"]:
                processed_words.append(word.upper())
            # Handle words with internal connectors like "Food&Drink", "Health-Medical"
            elif any(c in word for c in ['&', '-', '/']):
                # Split by connectors, title-case word parts, and re-join with connectors
                parts = re.split(r'([&\-/])', word) # Capture the delimiters
                rejoined_parts = []
                for p in parts:
                    if p.strip() and not re.match(r'^[&\-/]$', p): # If it's a word part, title case
                        rejoined_parts.append(p.strip().title())
                    else: # If it's a connector or empty, append as is
                        rejoined_parts.append(p)
                processed_words.append("".join(rejoined_parts))
            else:
                processed_words.append(word.title())

        return " ".join(processed_words)

    def __hash__(self):
        """Hash based on name for deduplication."""
        return hash(self.name)

    def __eq__(self, other):
        """Equality based on name."""
        if isinstance(other, Category):
            return self.name == other.name
        return False