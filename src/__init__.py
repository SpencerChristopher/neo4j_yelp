# src/__init__.py
"""
Main application package.
Contains all core business logic and data models.
"""

# Import models for easier access
from .models import Business, User, Review, Category

# You can also expose key application components here
# For example, if you have app factories or core functions:
# from .app import create_app
# from .database import db

__all__ = [
    # Models
    "Business",
    "User",
    "Review",
    "Category",

    # Core application components (add as you build them)
    # "create_app",
    # "db",
]
