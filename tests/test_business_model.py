import pandas as pd
import logging
import sys
import os
from pydantic import ValidationError, confloat, conint # Import confloat, conint
import pytest
from typing import List, Dict, Any

from models import Business, Location # Import Location as well

# Configure basic logging for the test script
logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = 'Data'
BUSINESS_CSV = os.path.join(DATA_DIR, 'business_small.csv')
SAMPLE_SIZE = 200 # Number of lines to sample from the CSV

@pytest.fixture(scope="module")
def sample_raw_data() -> List[Dict[str, Any]]:
    """Loads a sample of raw business data from business_small.csv."""
    if not os.path.exists(BUSINESS_CSV):
        pytest.fail(f"Error: {BUSINESS_CSV} not found. Ensure 'Data' directory exists and contains the CSV.")

    try:
        df_sample = pd.read_csv(BUSINESS_CSV, nrows=SAMPLE_SIZE).fillna('').to_dict(orient='records')
        logger.info(f"Successfully loaded {len(df_sample)} sample rows from {BUSINESS_CSV}.")
        return df_sample
    except Exception as e:
        pytest.fail(f"Failed to load sample data from {BUSINESS_CSV}: {e}")


def test_business_model_valid_data(sample_raw_data: List[Dict[str, Any]]):
    """Tests validation of a few valid rows from the sample data."""
    logger.info("\n--- Testing Business Pydantic Model with Valid Data ---")
    
    # Take a few rows that are expected to be valid
    valid_rows_to_test = sample_raw_data[:5] 
    assert len(valid_rows_to_test) > 0, "No valid sample data to test."

    for i, raw_row in enumerate(valid_rows_to_test):
        try:
            business = Business(**raw_row)
            logger.info(f"Row {i+1}: Valid Business data successfully validated (business_id={business.business_id}).")
            assert business.city == raw_row['city'].title() if raw_row['city'] else None # Check casing, now city is Optional
            assert business.state == raw_row['state'].upper() # Check casing, state is Required
            assert business.postal_code == (raw_row['postal_code'] if raw_row['postal_code'] != '' else None) # Check postal_code handling
            assert business.location.latitude == raw_row['latitude']
            assert business.location.longitude == raw_row['longitude']
        except ValidationError as e:
            pytest.fail(f"Row {i+1}: Validation unexpectedly failed for business_id={raw_row.get('business_id', 'N/A')}. Errors: {e.json()}")
        except AssertionError as e:
            pytest.fail(f"Row {i+1}: Assertion failed for business_id={raw_row.get('business_id', 'N/A')}. Error: {e}")


def test_business_model_invalid_data(sample_raw_data: List[Dict[str, Any]]):
    """Tests validation of intentionally manipulated data with known bad forms."""
    logger.info("\n--- Testing Business Pydantic Model with Intentionally Manipulated Data ---")

    manipulated_data_tests = [
        # Test 1: Invalid stars, review_count, is_open
        {
            **sample_raw_data[0], # Take a valid row and mess it up
            "business_id": "test_bad_1",
            "stars": 6.0, # Invalid range
            "review_count": -10, # Invalid range
            "is_open": 5 # Invalid range
        },
        # Test 2: Missing required field (name) - name is str, so None will fail
        {
            **sample_raw_data[1],
            "business_id": "test_bad_2",
            "name": None 
        },
        # Test 3: Invalid type for latitude
        {
            **sample_raw_data[2],
            "business_id": "test_bad_3",
            "latitude": "not_a_float" # Invalid type
        },
        # Test 4: Postal code as "" (valid conversion to None)
        {
            **sample_raw_data[3],
            "business_id": "test_bad_4",
            "postal_code": "" 
        },
        # Test 5: Latitude out of range (e.g., > 90)
        {
            **sample_raw_data[4],
            "business_id": "test_bad_5",
            "latitude": 91.0 
        },
        # Test 6: Latitude and Longitude are None (valid now for Location model)
        {
            **sample_raw_data[0],
            "business_id": "test_valid_none_lat_lon",
            "latitude": None,
            "longitude": None
        },
        # Test 7: Missing state (REQUIRED field)
        {
            **sample_raw_data[1],
            "business_id": "test_bad_state",
            "state": None # state is str, so None will fail
        },
        # Test 8: No city AND no postal_code (fails require_minimum_location)
        {
            **sample_raw_data[2],
            "business_id": "test_bad_min_location",
            "city": None,
            "postal_code": None
        }
    ]

    for i, bad_row in enumerate(manipulated_data_tests):
        business_id = bad_row.get('business_id', 'N/A')
        logger.info(f"Manipulated Test {i+1}: Attempting validation for business_id={business_id}")
        try:
            business = Business(**bad_row)
            if business_id == "test_bad_4": # This is expected to pass (postal code conversion)
                logger.info(f"Manipulated Test {i+1}: Correctly passed validation for postal_code conversion. {business.postal_code=}")
                assert business.postal_code is None
            elif business_id == "test_valid_none_lat_lon": # This is expected to pass (latitude/longitude are None)
                logger.info(f"Manipulated Test {i+1}: Correctly passed validation for None latitude/longitude. {business.location.latitude=} {business.location.longitude=}")
                assert business.location is not None
                assert business.location.latitude is None
                assert business.location.longitude is None
            else:
                pytest.fail(f"Manipulated Test {i+1}: UNEXPECTED SUCCESS - Bad data passed validation! {business}")
        except ValidationError as e:
            if business_id == "test_bad_4" or business_id == "test_valid_none_lat_lon": # These should NOT fail
                 pytest.fail(f"Manipulated Test {i+1}: UNEXPECTED FAILURE - Data that should pass failed validation! Errors: {e.json()}")
            logger.info(f"Manipulated Test {i+1}: Correctly failed validation. Errors: {e.errors()}")
            # Assert specific errors for known bad forms
            if business_id == "test_bad_1":
                assert any(err["loc"][0] == "stars" and "less_than_equal" in err["type"] for err in e.errors())
                assert any(err["loc"][0] == "review_count" and "greater_than_equal" in err["type"] for err in e.errors())
                assert any(err["loc"][0] == "is_open" and "less_than_equal" in err["type"] for err in e.errors())
            elif business_id == "test_bad_2":
                assert any(err["loc"][0] == "name" and "string_type" in err["type"] for err in e.errors())
            elif business_id == "test_bad_3":
                assert any(err["loc"] == ('location', 'latitude') and "float_parsing" in err["type"] for err in e.errors())
            elif business_id == "test_bad_5":
                assert any("Input should be less than or equal to 90" in err["msg"] for err in e.errors())
                assert any(err["loc"] == ('location', 'latitude') for err in e.errors())
            elif business_id == "test_bad_state":
                assert any(err["loc"][0] == "state" and "string_type" in err["type"] for err in e.errors())
            elif business_id == "test_bad_min_location":
                assert any("value_error" in err["type"] and "Business must have at least one of: city or postal_code" in err["msg"] for err in e.errors())
            logger.info(f"Manipulated Test {i+1}: Assertions for specific errors passed.")
        except AssertionError as e:
            pytest.fail(f"Manipulated Test {i+1}: Assertion failed. Error: {e}")
        except Exception as e:
            pytest.fail(f"Manipulated Test {i+1}: Unexpected general error: {e}")

# This __main__ block is typically not used when running with pytest,
# but can be useful for direct script execution if desired.
if __name__ == "__main__":
    # To run these tests directly from the script (without pytest command),
    # you would typically call pytest.main().
    # For simplicity, we'll just log an info message.
    logger.info("Run this file using 'poetry run pytest src/test_business_model.py' for proper testing.")
    # Example of how to run pytest programmatically
    # import pytest
    # pytest.main([__file__])
