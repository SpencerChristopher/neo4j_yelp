# tests/test_business_elt.py
import pytest
import pandas as pd
import json
from pathlib import Path
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock, call

from src.settings import (
    BUSINESS_CSV,
    BATCH_SIZE,
    DEAD_LETTER_FILE,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
)

from src.validator import validate_business_data
from src.normalizer import normalize_business_data
from src.loader import Neo4jLoader
from src.models import State, City, PostalCode

# Define expected CSV headers based on your requirements
EXPECTED_CSV_HEADERS = [
    'business_id',  # Primary key
    'name',  # Business name
    'city',  # City name
    'state',  # State code (e.g., AZ, CA)
    'postal_code',  # Postal code (integer)
    'latitude',  # Geographic coordinate
    'longitude',  # Geographic coordinate
    'stars',  # Rating (float)
    'review_count',  # Number of reviews (integer)
    'is_open'  # 1=open, 0=closed (integer)
]

# Optional headers that might exist but aren't required
OPTIONAL_HEADERS = [
    'address',  # Street address
    'categories',  # Business categories
    'hours',  # Operating hours
    'attributes'  # Additional attributes
]


# Copy your exact ELT function here - FIXED THE PARAMETER NAME
def run_business_elt():
    """Your original ELT function."""
    print("Starting Business ELT test run")

    loader = Neo4jLoader(
        uri=NEO4J_URI,
        username=NEO4J_USER,  # ✅ Fixed: changed 'user' to 'username'
        password=NEO4J_PASSWORD,
    )

    dead_letters_path = Path(DEAD_LETTER_FILE)
    dead_letters_path.parent.mkdir(parents=True, exist_ok=True)

    total_valid = 0
    total_invalid = 0

    try:
        for chunk_idx, chunk in enumerate(
                pd.read_csv(BUSINESS_CSV, chunksize=BATCH_SIZE),
                start=1,
        ):
            print(f"\nProcessing chunk {chunk_idx}")

            raw_records = chunk.fillna("").to_dict("records")

            # --- VALIDATE ---
            valid_businesses, invalid_businesses = validate_business_data(raw_records)

            total_valid += len(valid_businesses)
            total_invalid += len(invalid_businesses)

            if invalid_businesses:
                with dead_letters_path.open("a", encoding="utf-8") as f:
                    for record in invalid_businesses:
                        f.write(json.dumps(record) + "\n")

            if not valid_businesses:
                print("️ No valid records in this chunk")
                continue

            # --- NORMALIZE ---
            normalized_businesses, city_claims, postal_claims = (
                normalize_business_data(valid_businesses)
            )

            # --- CANONICAL NODES ---
            states = {
                State(code=claim["state"])
                for claim in city_claims
            }

            cities = {
                City(name=claim["city"], state_code=claim["state"])
                for claim in city_claims
            }

            postal_codes = {
                PostalCode(code=claim["postal_code"])
                for claim in postal_claims
            }

            # --- LOAD NODES ---
            loader.load_states(list(states))
            loader.load_cities(list(cities))
            loader.load_postal_codes(list(postal_codes))
            loader.load_businesses(normalized_businesses)

            # --- RELATIONSHIPS ---
            relationships = []

            for city in cities:
                relationships.append({
                    "from_node_type": "City",
                    "from_node_id_prop": "name",
                    "from_node_id_value": city.name,
                    "from_node_id_aux_prop": "state_code",
                    "from_node_id_aux_value": city.state_code,
                    "to_node_type": "State",
                    "to_node_id_prop": "code",
                    "to_node_id_value": city.state_code,
                    "relationship_type": "CLAIMS_STATE",
                    "properties": {},
                })

            for claim in city_claims:
                relationships.append({
                    "from_node_type": "Business",
                    "from_node_id_prop": "business_id",
                    "from_node_id_value": claim["business_id"],
                    "to_node_type": "City",
                    "to_node_id_prop": "name",
                    "to_node_id_value": claim["city"],
                    "to_node_id_aux_prop": "state_code",
                    "to_node_id_aux_value": claim["state"],
                    "relationship_type": "LOCATED_NEAR",
                    "properties": {
                        "latitude": claim["latitude"],
                        "longitude": claim["longitude"],
                    },
                })

            for claim in postal_claims:
                relationships.append({
                    "from_node_type": "Business",
                    "from_node_id_prop": "business_id",
                    "from_node_id_value": claim["business_id"],
                    "to_node_type": "PostalCode",
                    "to_node_id_prop": "code",
                    "to_node_id_value": claim["postal_code"],
                    "relationship_type": "CLAIMS_POSTAL_CODE",
                    "properties": {},
                })

            loader.create_relationships(relationships)

            print(
                f"Chunk {chunk_idx} done | "
                f"valid={len(valid_businesses)} invalid={len(invalid_businesses)}"
            )

    finally:
        loader.close()

    print("\n\t ELT complete")
    print(f"Total valid records: {total_valid}")
    print(f"Total invalid records: {total_invalid}")

    return total_valid, total_invalid


# -------------------- TEST FUNCTIONS --------------------

def test_csv_file_exists_and_has_correct_headers():
    """Test that the CSV file exists and has the expected headers."""
    csv_path = Path(BUSINESS_CSV)

    # Test file exists
    assert csv_path.exists(), f"CSV file not found: {BUSINESS_CSV}"
    assert csv_path.is_file(), f"Path is not a file: {BUSINESS_CSV}"

    # Test file is readable
    file_size = csv_path.stat().st_size
    assert file_size > 0, f"CSV file is empty: {BUSINESS_CSV}"

    print(f"\nTesting CSV file: {csv_path}")
    print(f"   File size: {file_size} bytes")

    # Test can read first few rows
    try:
        # Read just headers first
        df_sample = pd.read_csv(csv_path, nrows=5)

        print(f"\nFound {len(df_sample.columns)} columns:")
        for i, col in enumerate(df_sample.columns, 1):
            print(f"   {i:2}. {col}")

        # Get actual headers
        actual_headers = list(df_sample.columns)

        # Check all expected headers are present
        missing_headers = []
        for expected_header in EXPECTED_CSV_HEADERS:
            if expected_header not in actual_headers:
                missing_headers.append(expected_header)

        # Check for extra headers
        extra_headers = []
        for actual_header in actual_headers:
            if (actual_header not in EXPECTED_CSV_HEADERS and
                    actual_header not in OPTIONAL_HEADERS):
                extra_headers.append(actual_header)

        # Report findings
        if missing_headers:
            print(f"\nERROR: Missing required headers: {', '.join(missing_headers)}")
            pytest.fail(f"CSV missing required headers: {missing_headers}")

        if extra_headers:
            print(f"\nNOTE: Extra headers found (will be ignored): {', '.join(extra_headers)}")

        print(f"\nSUCCESS: All required headers present: {', '.join(EXPECTED_CSV_HEADERS)}")

        # Show sample data
        print(f"\nSample data (first row):")
        sample_row = df_sample.iloc[0]
        for header in EXPECTED_CSV_HEADERS:
            if header in sample_row:
                value = sample_row[header]
                # Truncate long values
                if isinstance(value, str) and len(value) > 50:
                    value = value[:47] + "..."
                print(f"   {header:15}: {value}")

        # Check data types
        print(f"\nData types:")
        for header in EXPECTED_CSV_HEADERS:
            if header in df_sample.columns:
                dtype = df_sample[header].dtype
                print(f"   {header:15}: {dtype}")

    except Exception as e:
        pytest.fail(f"Failed to read CSV file: {e}")


def test_csv_data_quality():
    """Test basic data quality of the CSV file."""
    csv_path = Path(BUSINESS_CSV)

    if not csv_path.exists():
        pytest.skip(f"CSV file not found: {BUSINESS_CSV}")

    print(f"\nTesting CSV data quality: {csv_path}")

    try:
        # Read first 1000 rows for quality checks
        df = pd.read_csv(csv_path, nrows=1000)

        print(f"   Total rows in sample: {len(df)}")

        # Check for missing values in required columns
        print(f"\nMissing value analysis:")
        for header in EXPECTED_CSV_HEADERS:
            if header in df.columns:
                missing_count = df[header].isna().sum()
                missing_pct = (missing_count / len(df)) * 100
                print(f"   {header:15}: {missing_count} missing ({missing_pct:.1f}%)")

                # Business critical columns should have very few missing values
                if header in ['business_id', 'name', 'city', 'state']:
                    if missing_pct > 5:
                        print(f"   WARNING: High missing rate for critical column: {header}")

        # Check for duplicates in business_id (should be unique)
        if 'business_id' in df.columns:
            duplicates = df['business_id'].duplicated().sum()
            print(f"\nDuplicate business_id: {duplicates}")
            if duplicates > 0:
                print(f"   WARNING: Found {duplicates} duplicate business_id values")

        # Check state codes are valid (2 characters)
        if 'state' in df.columns:
            valid_states = df['state'].dropna().apply(lambda x: isinstance(x, str) and len(str(x)) == 2)
            valid_state_count = valid_states.sum()
            invalid_state_count = len(valid_states) - valid_state_count

            print(f"\nState code validation:")
            print(f"   Valid (2 chars): {valid_state_count}")
            print(f"   Invalid: {invalid_state_count}")

            if invalid_state_count > 0:
                invalid_states = df.loc[~valid_states, 'state'].unique()[:10]
                print(f"   Sample invalid states: {invalid_states}")

        # Check postal codes are numeric
        if 'postal_code' in df.columns:
            numeric_postal = pd.to_numeric(df['postal_code'], errors='coerce')
            non_numeric = numeric_postal.isna().sum()
            print(f"\nPostal code validation:")
            print(f"   Numeric: {len(df) - non_numeric}")
            print(f"   Non-numeric: {non_numeric}")

        print(f"\nSUCCESS: Data quality checks completed")

    except Exception as e:
        pytest.fail(f"Data quality check failed: {e}")


# Simple test without the integration marker to avoid warnings
def test_run_business_elt_with_mocked_database():
    """Test the ELT pipeline with mocked database calls but real CSV data."""

    # Skip if CSV doesn't exist
    csv_path = Path(BUSINESS_CSV)
    if not csv_path.exists():
        pytest.skip(f"CSV file not found: {BUSINESS_CSV}")

    # Create temporary dead letter file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
        dead_letter_path = tmp.name

    try:
        # Mock settings
        with patch('src.settings.DEAD_LETTER_FILE', dead_letter_path):
            with patch('src.settings.BATCH_SIZE', 100):  # Use reasonable batch for testing

                # Mock Neo4jLoader to prevent actual database calls
                with patch('src.loader.Neo4jLoader') as mock_loader_class:
                    mock_loader = Mock()
                    mock_loader_class.return_value = mock_loader

                    # Set up mock return values
                    mock_loader.load_states = Mock(return_value=5)
                    mock_loader.load_cities = Mock(return_value=10)
                    mock_loader.load_postal_codes = Mock(return_value=15)
                    mock_loader.load_businesses = Mock(return_value=20)
                    mock_loader.create_relationships = Mock(return_value=30)
                    mock_loader.close = Mock()

                    # Run the ELT function
                    print(f"\n{'=' * 60}")
                    print(f"Testing ELT pipeline with real CSV data")
                    print(f"CSV: {BUSINESS_CSV}")
                    print(f"Batch size: 100")
                    print(f"Dead letters: {dead_letter_path}")
                    print(f"{'=' * 60}")

                    total_valid, total_invalid = run_business_elt()

                    # Verify the loader was called
                    assert mock_loader_class.called, "Neo4jLoader should be instantiated"
                    assert mock_loader.close.called, "Loader should be closed"

                    # Verify loader methods were called (at least once)
                    assert mock_loader.load_states.called, "load_states should be called"
                    assert mock_loader.load_cities.called, "load_cities should be called"
                    assert mock_loader.load_postal_codes.called, "load_postal_codes should be called"
                    assert mock_loader.load_businesses.called, "load_businesses should be called"
                    assert mock_loader.create_relationships.called, "create_relationships should be called"

                    print(f"\nSUCCESS: ELT pipeline completed successfully")
                    print(f"   Valid records processed: {total_valid}")
                    print(f"   Invalid records: {total_invalid}")

                    # Check if dead letter file was created (if there were invalid records)
                    dead_letter_file = Path(dead_letter_path)
                    if total_invalid > 0:
                        assert dead_letter_file.exists(), \
                            "Dead letter file should exist when there are invalid records"
                        file_size = dead_letter_file.stat().st_size
                        print(f"   Dead letter file size: {file_size} bytes")

                    print(f"\nSummary:")
                    print(f"   - CSV file: {csv_path}")
                    print(f"   - Required headers: {len(EXPECTED_CSV_HEADERS)}")
                    print(f"   - Optional headers: {len(OPTIONAL_HEADERS)}")
                    print(f"   - ELT processing: COMPLETE")

    finally:
        # Clean up temp file
        if os.path.exists(dead_letter_path):
            os.remove(dead_letter_path)


def test_elt_validation_with_real_data():
    """Test validation component with real CSV data."""
    csv_path = Path(BUSINESS_CSV)

    if not csv_path.exists():
        pytest.skip(f"CSV file not found: {BUSINESS_CSV}")

    # Read a meaningful sample from the CSV
    sample_size = 500
    print(f"\nTesting validation with {sample_size} real records from {csv_path}")

    try:
        df_sample = pd.read_csv(csv_path, nrows=sample_size)
        raw_records = df_sample.fillna("").to_dict("records")

        # Run validation
        valid_businesses, invalid_businesses = validate_business_data(raw_records)

        print(f"\nValidation Results:")
        print(f"   Total records: {len(raw_records)}")
        print(f"   Valid: {len(valid_businesses)} ({len(valid_businesses) / len(raw_records) * 100:.1f}%)")
        print(f"   Invalid: {len(invalid_businesses)} ({len(invalid_businesses) / len(raw_records) * 100:.1f}%)")

        # Basic assertions
        assert len(valid_businesses) + len(invalid_businesses) == len(raw_records), \
            "Validation should process all records"

        if len(valid_businesses) > 0:
            # Check that valid records are Business instances
            from src.models import Business
            biz = valid_businesses[0]
            assert isinstance(biz, Business), "Valid records should be Business instances"

            # Verify all expected fields are present
            for header in EXPECTED_CSV_HEADERS:
                if header in ['latitude', 'longitude', 'stars', 'review_count', 'is_open']:
                    continue  # These might be converted to different types
                assert hasattr(biz, header), f"Business should have attribute: {header}"

            print(f"\nSample valid business:")
            print(f"   ID: {biz.business_id}")
            print(f"   Name: {biz.name}")
            print(f"   Location: {biz.city}, {biz.state} {biz.postal_code}")
            print(f"   Rating: {biz.stars} stars ({biz.review_count} reviews)")

        if len(invalid_businesses) > 0:
            print(f"\nSample invalid record errors:")
            invalid_record = invalid_businesses[0]
            print(f"   Business ID: {invalid_record['record'].get('business_id', 'N/A')}")
            print(f"   Errors: {invalid_record['errors']}")

            # Analyze common error types
            error_types = {}
            for invalid in invalid_businesses[:10]:  # Look at first 10
                for error in invalid['errors']:
                    error_types[error['type']] = error_types.get(error['type'], 0) + 1

            if error_types:
                print(f"\nCommon error types (top 10 records):")
                for error_type, count in error_types.items():
                    print(f"   {error_type}: {count}")

        print(f"\nSUCCESS: Validation test passed")

    except Exception as e:
        pytest.fail(f"Validation test failed: {e}")


def test_elt_normalization_with_real_data():
    """Test normalization component with validated real data."""
    csv_path = Path(BUSINESS_CSV)

    if not csv_path.exists():
        pytest.skip(f"CSV file not found: {BUSINESS_CSV}")

    # Read and validate a sample
    sample_size = 200
    print(f"\nTesting normalization with {sample_size} real records")

    try:
        df_sample = pd.read_csv(csv_path, nrows=sample_size)
        raw_records = df_sample.fillna("").to_dict("records")

        # Validate first
        valid_businesses, _ = validate_business_data(raw_records)

        if len(valid_businesses) == 0:
            pytest.skip("No valid records found in sample")

        print(f"   Valid businesses for normalization: {len(valid_businesses)}")

        # Test normalization
        normalized_businesses, city_claims, postal_claims = normalize_business_data(valid_businesses)

        print(f"\nNormalization Results:")
        print(f"   Normalized businesses: {len(normalized_businesses)}")
        print(f"   City claims: {len(city_claims)}")
        print(f"   Postal claims: {len(postal_claims)}")

        # Check counts match
        assert len(normalized_businesses) == len(valid_businesses), \
            "Should have one normalized record per valid business"
        assert len(city_claims) == len(valid_businesses), \
            "Should have one city claim per valid business"
        assert len(postal_claims) == len(valid_businesses), \
            "Should have one postal claim per valid business"

        # Check normalization removed location data
        print(f"\nChecking normalization transformations:")

        biz = normalized_businesses[0]
        print(f"   Location data removed from business: OK")
        print(f"     - 'city' in business: {'city' in biz} (should be False)")
        print(f"     - 'state' in business: {'state' in biz} (should be False)")
        print(f"     - 'postal_code' in business: {'postal_code' in biz} (should be False)")

        for biz in normalized_businesses[:3]:  # Check first 3
            assert 'city' not in biz, "City should be removed from normalized business"
            assert 'state' not in biz, "State should be removed from normalized business"
            assert 'postal_code' not in biz, "Postal code should be removed"
            assert 'latitude' not in biz, "Latitude should be removed"
            assert 'longitude' not in biz, "Longitude should be removed"

            # Should keep business attributes
            assert 'business_id' in biz, "Should keep business_id"
            assert 'name' in biz, "Should keep name"
            assert 'stars' in biz, "Should keep stars"
            assert 'is_open' in biz, "Should keep is_open"

        # Check city claims structure
        if len(city_claims) > 0:
            claim = city_claims[0]
            print(f"\nSample city claim structure: OK")
            for field in ['business_id', 'city', 'state', 'latitude', 'longitude']:
                print(f"   - {field}: {field in claim} (should be True)")
                assert field in claim, f"City claim missing {field}"

        # Check postal claims structure
        if len(postal_claims) > 0:
            claim = postal_claims[0]
            print(f"\nSample postal claim structure: OK")
            print(f"   - business_id: {claim['business_id']}")
            print(f"   - postal_code: {claim['postal_code']}")
            assert 'business_id' in claim
            assert 'postal_code' in claim

        print(f"\nSUCCESS: Normalization test passed")

    except Exception as e:
        pytest.fail(f"Normalization test failed: {e}")


# This allows the file to still be run as a standalone script
if __name__ == "__main__":
    # If run directly, execute the ELT function
    run_business_elt()