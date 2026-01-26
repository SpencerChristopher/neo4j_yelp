"""
Unit tests for data models.
"""
import pytest
from unittest.mock import patch
import logging
from datetime import datetime

from pydantic import ValidationError
from src.models import (
    Business, User, Review, City, State,
    PostalCode, Category, Friend, Location
)


class TestBusinessModel:
    """Minimal tests for the Business model."""

    @pytest.mark.unit
    def test_business_creation_and_basic_fields(self, sample_business_data):
        """Test creating a Business instance and verify basic field assignment."""
        business = Business(**sample_business_data)
        assert business.business_id == "abc123"
        assert business.name == "Test Restaurant"
        assert business.stars == 4.5
        assert business.review_count == 100
        assert business.is_open == 1
        assert isinstance(business.location, Location)
        assert business.location.latitude == 40.7128

    @pytest.mark.unit
    def test_business_state_validation_basic(self, sample_business_data):
        """Test basic state field validation."""
        with pytest.raises(ValidationError):
            Business(**{**sample_business_data, "state": "INVALID"})
            # Invalid: None (state is not optional)
            with pytest.raises(ValidationError, match="Input should be a valid string"):
                Business(**{**sample_business_data, "state": None})

    @pytest.mark.unit
    def test_business_postal_code_normalization_basic(self, sample_business_data):
        """Test basic postal code normalization."""
        business = Business(**{**sample_business_data, "postal_code": "A1B 2C3"})
        assert business.postal_code == "A1B2C3"


class TestUserModel:
    """Minimal tests for the User model."""

    @pytest.mark.unit
    def test_user_creation_and_basic_fields(self, sample_user_data):
        """Test creating a User instance and verify basic field assignment."""
        user = User(**sample_user_data)
        assert user.user_id == "user123"
        assert user.name == "John Doe"
        assert isinstance(user.yelping_since, datetime)
        assert user.total_compliments == 0 # Corrected: All compliments are 0 in sample data

    @pytest.mark.unit
    def test_user_yelping_since_parsing_basic(self, sample_user_data):
        """Test yelping_since parsing."""
        user = User(**{**sample_user_data, "yelping_since": "26/02/2014 23:24"})
        assert user.yelping_since.year == 2014
        with patch.object(logging.getLogger('src.models.user'), 'warning') as mock_warn:
            User(**{**sample_user_data, "yelping_since": "not a date"})
            mock_warn.assert_called_once()


class TestReviewModel:
    """Minimal tests for the Review model."""

    @pytest.mark.unit
    def test_review_creation_and_basic_fields(self, sample_review_data):
        """Test creating a Review instance and verify basic field assignment."""
        review = Review(**sample_review_data)
        assert review.review_id == "rev123"
        assert review.stars == 5
        assert isinstance(review.date, datetime)
        assert review.engagement_score == 17.0

    @pytest.mark.unit
    def test_review_date_parsing_basic(self, sample_review_data):
        """Test review date parsing."""
        review = Review(**{**sample_review_data, "date": "15/01/2023 12:30"})
        assert review.date.year == 2023
        with pytest.raises(ValidationError):
            Review(**{**sample_review_data, "date": "invalid date"})


class TestCategoryModel:
    """Minimal tests for the Category model."""

    @pytest.mark.unit
    def test_category_creation_and_name(self):
        """Test creating a Category instance and verifying name."""
        category = Category(name="Restaurants")
        assert category.name == "Restaurants"

    @pytest.mark.unit
    def test_category_name_normalization_basic(self):
        """Test basic category name normalization."""
        category = Category(name="  health & MEDICAL  ")
        assert category.name == "Health & Medical"
        category = Category(name="food/drink-fast") # This was a failing test case
        assert category.name == "Food/Drink-Fast"


class TestCityModel:
    """Minimal tests for the City model."""

    @pytest.mark.unit
    def test_city_creation_and_fields(self):
        """Test creating a City instance and verifying fields."""
        city = City(name="Phoenix", state_code="AZ")
        assert city.name == "Phoenix"
        assert city.state_code == "AZ"

    @pytest.mark.unit
    def test_city_hashing_and_equality(self):
        """Test hashing and equality for deduplication."""
        city1 = City(name="Phoenix", state_code="AZ")
        city2 = City(name="phoenix", state_code="AZ") # Normalization should make it equal
        assert city1 == city2


class TestStateModel:
    """Minimal tests for the State model."""

    @pytest.mark.unit
    def test_state_creation_and_code(self):
        """Test creating a State instance and verifying code."""
        state = State(code="AZ")
        assert state.code == "AZ"

    @pytest.mark.unit
    def test_state_hashing_and_equality(self):
        """Test hashing and equality for deduplication."""
        state1 = State(code="AZ")
        state2 = State(code="az") # Normalization should make it equal (after fix in model)
        assert state1 == state2


class TestPostalCodeModel:
    """Minimal tests for the PostalCode model."""

    @pytest.mark.unit
    def test_postal_code_creation_and_code(self):
        """Test creating a PostalCode instance and verifying code."""
        pc = PostalCode(code="12345")
        assert pc.code == "12345"

    @pytest.mark.unit
    def test_postal_code_normalization_basic(self):
        """Test basic postal code normalization."""
        pc = PostalCode(code="A1B 2C3")
        assert pc.code == "A1B2C3"


class TestFriendModel:
    """Minimal tests for the Friend model."""

    @pytest.mark.unit
    def test_friend_creation_and_normalization(self):
        """Test creating a Friend instance and user_id normalization (sorting)."""
        friend1 = Friend(user1="userB", user2="userA")
        assert friend1.user1 == "userA"
        assert friend1.user2 == "userB"

    @pytest.mark.unit
    def test_friend_self_loop_prevention_basic(self):
        """Test self-loop prevention."""
        with pytest.raises(ValidationError, match="User cannot be friends with themselves"):
            Friend(user1="userA", user2="userA")


class TestLocationModel:
    """Minimal tests for the the Location model."""

    @pytest.mark.unit
    def test_location_creation_and_fields(self):
        """Test creating a Location instance and verifying fields."""
        loc = Location(latitude=12.34, longitude=56.78)
        assert loc.latitude == 12.34
        assert loc.longitude == 56.78

    @pytest.mark.unit
    def test_models_import(self):
        """Test that all models can be imported correctly."""
        # Verify all classes are imported
        assert Business is not None
        assert User is not None
        assert Review is not None
        assert City is not None
        assert Category is not None
        assert State is not None
        assert PostalCode is not None
        assert Friend is not None
        assert Location is not None

