"""
This file makes the 'models' directory a Python package and exposes the primary model classes
for easier importing.

Instead of:
from models.business import Business

You can do:
from models import Business
"""
from .business import Business, Location
# When User and Review models are created, they will be imported here as well.
# from .user import User
# from .review import Review
