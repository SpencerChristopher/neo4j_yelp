"""
This file makes the 'models' directory a Python package and exposes the primary model classes
for easier importing.

Instead of:
from models.business import Business

You can do:
from models import Business
"""
# src/models/__init__.py
from .business import Business, Location
from .user import User
from .review import Review
from .city import City
from .state import State
from .postal_code import PostalCode
from .category import Category
from .friend import Friend

__all__ = [
    "Business",
    "Location",
    "User",
    "Review",
    "City",
    "State",
    "PostalCode",
    "Category",
    "Friend",
]