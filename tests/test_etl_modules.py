import pytest
from pydantic import ValidationError
from src.models import CanonicalCityState, City, State, PostalCode, Business, Location
from src.validator import validate_business_data, validate_canonical_city_state_data
from src.normalizer import normalize_business_data, normalize_canonical_city_state_data
from src.loader import Neo4jLoader
import os
import pandas as pd
from unittest.mock import MagicMock, patch, call


# --- Fixtures (will add more as needed) ---

@pytest.fixture
def mock_business_raw_data():
    return [
        {"business_id": "b1", "name": "Test Business 1", "city": "phoenix", "state": "az", "postal_code": 85001,
         "latitude": 33.1, "longitude": -112.1, "stars": 3.5, "review_count": 10, "is_open": 1},
        {"business_id": "b2", "name": "Test Business 2", "city": "Scottsdale", "state": "AZ", "postal_code": 85250,
         "latitude": 33.2, "longitude": -112.2, "stars": 4.0, "review_count": 20, "is_open": 0},
        {"business_id": "b3", "name": "No City Or Postal", "city": None, "state": "CA", "postal_code": None,
         "latitude": 34.0, "longitude": -118.0, "stars": 3.0, "review_count": 5, "is_open": 1},
        # Should fail validation
        {"business_id": "b4", "name": "Invalid State", "city": "Reno", "state": "NV", "postal_code": 89501,
         "latitude": 39.5, "longitude": -119.8, "stars": 4.5, "review_count": 15, "is_open": 1},
        # State now "NV" for consistency
        {"business_id": "b5", "name": "Missing State", "city": "Las Vegas", "state": None, "postal_code": 89101,
         "latitude": 36.1, "longitude": -115.1, "stars": 2.5, "review_count": 8, "is_open": 1},
        # Should fail validation
        {"business_id": "b6", "name": "Invalid Postal", "city": "Bad", "state": "AZ", "postal_code": 999999,
         "latitude": 33.1, "longitude": -112.1, "stars": 3.5, "review_count": 10, "is_open": 1},
        # Should fail validation
        {"business_id": "b7", "name": "Good Business", "city": "Phoenix", "state": "AZ", "postal_code": 85001,
         "latitude": 33.1, "longitude": -112.1, "stars": 3.5, "review_count": 10, "is_open": 1},
    ]


@pytest.fixture
def mock_canonical_city_state_raw_data():
    return [
        {"city": "phoenix", "state_code": "az"},
        {"city": "Scottsdale", "state_code": "AZ"},
        {"city": "las vegas", "state_code": "nv"},
        {"city": "New York", "state_code": "NY"},
        {"city": "Invalid State Code", "state_code": "ABC"},  # Invalid
        {"city": None, "state_code": "CA"},  # Invalid - city missing
        {"city": "Los Angeles", "state_code": None},  # Invalid - state_code missing
        {"city": "Too Long State Code", "state_code": "LONG"},  # Invalid - state_code too long
        {"city": "Short State Code", "state_code": "S"},  # Invalid - state_code too short
        {"city": "Numbered State", "state_code": "A1"},  # Invalid - pattern mismatch
    ]


# --- Tests for src/models/canonical_city_state.py ---

def test_canonical_city_state_valid_data():
    data = {"city": "phoenix", "state_code": "az"}
    model = CanonicalCityState(**data)
    assert model.city == "Phoenix"
    assert model.state_code == "AZ"

    data_uppercase = {"city": "SCOTTSDALE", "state_code": "AZ"}
    model_upper = CanonicalCityState(**data_uppercase)
    assert model_upper.city == "Scottsdale"
    assert model_upper.state_code == "AZ"


def test_canonical_city_state_invalid_state_code_format():
    # string_too_short
    with pytest.raises(ValidationError) as exc_info:
        CanonicalCityState(city="Anytown", state_code="A")
    assert "string_too_short" in str(exc_info.value)

    # string_too_long
    with pytest.raises(ValidationError) as exc_info:
        CanonicalCityState(city="Anytown", state_code="AZZ")
    assert "string_too_long" in str(exc_info.value)

    # string_pattern_mismatch (only for cases that *cannot* be normalized to valid pattern, e.g., "A1")
    # 'az' will be normalized to 'AZ' by field_validator and then pass the pattern check.
    assert CanonicalCityState(city="Anytown",
                              state_code="az").state_code == "AZ"  # This should pass due to normalization

    with pytest.raises(ValidationError) as exc_info:
        CanonicalCityState(city="Anytown", state_code="A1")  # Contains non-alpha, still invalid
    assert "string_pattern_mismatch" in str(exc_info.value)


def test_canonical_city_state_missing_fields():
    with pytest.raises(ValidationError):
        CanonicalCityState(city="Missing State")  # Missing state_code

    with pytest.raises(ValidationError):
        CanonicalCityState(state_code="CA")  # Missing city

    with pytest.raises(ValidationError):
        CanonicalCityState()  # Missing both


# --- Tests for src/validator.py ---

def test_validate_business_data_valid(mock_business_raw_data):
    # Filter for known valid data
    valid_raw = [r for r in mock_business_raw_data if r["business_id"] in ["b1", "b2", "b7"]]
    valid_records, invalid_records = validate_business_data(valid_raw)

    assert len(valid_records) == 3
    assert len(invalid_records) == 0
    assert all(isinstance(rec, Business) for rec in valid_records)
    assert valid_records[0].name == "Test Business 1"
    assert valid_records[0].state == "AZ"


def test_validate_business_data_mixed_valid_invalid(mock_business_raw_data):
    valid_records, invalid_records = validate_business_data(mock_business_raw_data)

    # Expected valid: b1, b2, b4, b7
    assert len(valid_records) == 4
    assert all(isinstance(rec, Business) for rec in valid_records)
    assert {r.business_id for r in valid_records} == {"b1", "b2", "b4", "b7"}

    # Expected invalid: b3 (no city/postal), b5 (missing state), b6 (invalid postal)
    assert len(invalid_records) == 3
    assert {r["record"]["business_id"] for r in invalid_records} == {"b3", "b5", "b6"}


def test_validate_canonical_city_state_data_valid(mock_canonical_city_state_raw_data):
    # Valid records from mock_canonical_city_state_raw_data are those with correctly formatted city and state_code
    valid_raw_filtered = [
        r for r in mock_canonical_city_state_raw_data
        if r["state_code"] in ["az", "AZ", "nv", "NY"] and r["city"] is not None
    ]
    valid_records, invalid_records = validate_canonical_city_state_data(valid_raw_filtered)

    assert len(valid_records) == 4
    assert len(invalid_records) == 0
    assert all(isinstance(rec, CanonicalCityState) for rec in valid_records)
    assert valid_records[0].city == "Phoenix"
    assert valid_records[0].state_code == "AZ"


def test_validate_canonical_city_state_data_mixed_valid_invalid(mock_canonical_city_state_raw_data):
    valid_records, invalid_records = validate_canonical_city_state_data(mock_canonical_city_state_raw_data)

    # Expected valid: phoenix-az, Scottsdale-AZ, las vegas-nv, New York-NY
    assert len(valid_records) == 4
    assert all(isinstance(rec, CanonicalCityState) for rec in valid_records)

    # Expected invalid: ABC (invalid state_code), None city, None state_code, LONG, S, A1
    assert len(invalid_records) == 6
    invalid_city_names = {r["record"]["city"] for r in invalid_records if r["record"]["city"] is not None}
    invalid_state_codes = {r["record"]["state_code"] for r in invalid_records if r["record"]["state_code"] is not None}

    assert invalid_city_names == {"Invalid State Code", "Too Long State Code", "Short State Code", "Numbered State",
                                  "Los Angeles"}
    assert invalid_state_codes == {"ABC", "LONG", "S", "A1", "CA"}  # CA is here because its city is None
    assert any(
        rec["record"]["city"] is None for rec in invalid_records)  # Checks for {"city": None, "state_code": "CA"}
    assert any(rec["record"]["state_code"] is None for rec in
               invalid_records)  # Checks for {"city": "Los Angeles", "state_code": None}


# --- Tests for src/normalizer.py ---

def test_normalize_business_data(mock_business_raw_data):
    valid_businesses, _ = validate_business_data(mock_business_raw_data)

    (
        normalized_businesses,
        city_claims,
        postal_claims,
    ) = normalize_business_data(valid_businesses)

    # Test normalized_businesses
    assert len(normalized_businesses) == 4
    assert {b["business_id"] for b in normalized_businesses} == {"b1", "b2", "b4", "b7"}
    assert all("city" not in b and "state" not in b and "postal_code" not in b for b in normalized_businesses)
    assert all("stars" in b and "is_open" in b and "name" in b for b in normalized_businesses)

    # Test city_claims
    assert len(city_claims) == 4
    assert {c["business_id"] for c in city_claims} == {"b1", "b2", "b4", "b7"}
    assert all("city" in c and "state" in c and "latitude" in c and "longitude" in c for c in city_claims)

    # Test postal_claims
    assert len(postal_claims) == 4
    assert {pc["business_id"] for pc in postal_claims} == {"b1", "b2", "b4", "b7"}
    assert all("postal_code" in pc for pc in postal_claims)


def test_normalize_canonical_city_state_data(mock_canonical_city_state_raw_data):
    valid_cs, _ = validate_canonical_city_state_data(mock_canonical_city_state_raw_data)

    canonical_cities, canonical_states, relationships = normalize_canonical_city_state_data(valid_cs)

    # Test canonical_states
    assert len(canonical_states) == 3
    assert {s["code"] for s in canonical_states} == {"AZ", "NV", "NY"}

    # Test canonical_cities
    assert len(canonical_cities) == 4
    assert {f"{c['name']}-{c['state']}" for c in canonical_cities} == {"Phoenix-AZ", "Scottsdale-AZ", "Las Vegas-NV",
                                                                       "New York-NY"}

    # Test relationships (expected to be simple city-state dictionaries)
    assert len(relationships) == 4
    # Check a specific relationship's structure and content
    phoenix_rel = next(r for r in relationships if r["city"] == "Phoenix")
    assert phoenix_rel["state"] == "AZ"
    # Ensure no 'relationship_type' key is present in these normalizer outputs
    assert "relationship_type" not in phoenix_rel


# --- Tests for src/loader.py ---

# Fixture to mock the Neo4j driver, session, and transaction for all loader tests
@pytest.fixture
def mock_neo4j_loader(monkeypatch):
    # Mock the driver itself and its methods to prevent actual DB connection during tests
    mock_driver_instance = MagicMock()
    mock_session = MagicMock()

    # Mock the transaction object itself, ensuring it has a mock 'run' method and 'consume'
    mock_transaction = MagicMock()
    mock_tx_run_result = MagicMock()

    # Configure mock_counters to return simple integer values
    mock_counters = MagicMock()
    mock_counters.nodes_created = 1
    mock_counters.relationships_created = 1
    mock_tx_run_result.consume.return_value.counters = mock_counters

    mock_transaction.run.return_value = mock_tx_run_result  # Make run return the mock result

    # Configure session.execute_write to call the provided function with the transaction mock
    mock_session.execute_write.side_effect = lambda func, *args, **kwargs: func(mock_transaction, *args, **kwargs)

    # Configure the driver to return the session mock in a context manager
    mock_driver_instance.session.return_value.__enter__.return_value = mock_session

    # Mock verify_connectivity to do nothing, preventing actual connection attempt during init
    mock_driver_instance.verify_connectivity.return_value = None

    # Patch neo4j.GraphDatabase.driver to return our mocked driver instance
    monkeypatch.setattr("neo4j.GraphDatabase.driver", lambda *args, **kwargs: mock_driver_instance)

    # Initialize Neo4jLoader, which will now use the mocked driver
    loader = Neo4jLoader("bolt://localhost:7687", "neo4j", "password")

    # Yield the loader AND the mock_transaction AND mock_session objects for assertions
    yield loader, mock_transaction, mock_session
    loader.close()  # Ensure close is called


def test_neo4j_loader_init_success():
    # Mock the driver creation
    with patch('neo4j.GraphDatabase.driver') as mock_driver_func:
        mock_driver = MagicMock()
        mock_driver_func.return_value = mock_driver

        # Initialize loader
        loader = Neo4jLoader("bolt://localhost:7687", "neo4j", "password")

        assert loader.driver is not None
        # Verify that verify_connectivity was called
        loader.driver.verify_connectivity.assert_called_once()
        loader.close()


def test_neo4j_loader_init_failure():
    # This test specifically checks for failure during initialization if verify_connectivity fails
    with patch('neo4j.GraphDatabase.driver') as mock_driver_func:
        mock_driver_instance = MagicMock()
        mock_driver_func.return_value = mock_driver_instance
        # Simulate a connection error during verify_connectivity
        mock_driver_instance.verify_connectivity.side_effect = Exception("Connection error")
        # Expect the exception to be raised
        with pytest.raises(Exception, match=r"^Connection error$"):
            Neo4jLoader("bolt://localhost:7687", "neo4j", "password")


def test_load_states(mock_neo4j_loader):
    try:
        loader, mock_transaction, mock_session = mock_neo4j_loader
    except ValueError as e:
        pytest.fail(f"Failed to unpack mock_neo4j_loader fixture: {e}")

    states = [State(code="AZ"), State(code="CA")]

    # Call the method
    loaded_count = loader.load_states(states)

    # Verify the result
    assert loaded_count == 2  # nodes_created + relationships_created = 2 + 0

    # Verify execute_write was called
    try:
        mock_session.execute_write.assert_called_once()
    except AssertionError as e:
        pytest.fail(f"execute_write was not called: {e}")

    # Get the function that was passed to execute_write
    func_passed = mock_session.execute_write.call_args[0][0]

    # Verify the transaction was used
    try:
        mock_transaction.run.assert_called_once()
    except AssertionError as e:
        pytest.fail(f"Transaction run was not called: {e}")

    # Check the query and data
    call_args, call_kwargs = mock_transaction.run.call_args
    query = call_args[0]
    data = call_kwargs.get('data', [])

    assert "MERGE (:State {code: state.code})" in query
    assert len(data) == 2
    assert data[0]["code"] == "AZ"
    assert data[1]["code"] == "CA"


def test_load_cities(mock_neo4j_loader):
    try:
        loader, mock_transaction, mock_session = mock_neo4j_loader
    except ValueError as e:
        pytest.fail(f"Failed to unpack mock_neo4j_loader fixture: {e}")

    cities = [City(name="Phoenix", state_code="AZ"), City(name="Tucson", state_code="AZ")]

    loaded_count = loader.load_cities(cities)

    assert loaded_count == 2
    try:
        mock_session.execute_write.assert_called_once()
    except AssertionError as e:
        pytest.fail(f"execute_write was not called: {e}")

    # Get the function that was passed to execute_write
    func_passed = mock_session.execute_write.call_args[0][0]

    try:
        mock_transaction.run.assert_called_once()
    except AssertionError as e:
        pytest.fail(f"Transaction run was not called: {e}")

    call_args, call_kwargs = mock_transaction.run.call_args
    query = call_args[0]
    data = call_kwargs.get('data', [])

    assert "MERGE (:City {name: city.name, state_code: city.state_code})" in query
    assert len(data) == 2
    assert data[0]["name"] == "Phoenix"
    assert data[0]["state_code"] == "AZ"


def test_load_postal_codes(mock_neo4j_loader):
    try:
        loader, mock_transaction, mock_session = mock_neo4j_loader
    except ValueError as e:
        pytest.fail(f"Failed to unpack mock_neo4j_loader fixture: {e}")

    postal_codes = [PostalCode(code=85001), PostalCode(code=90210)]

    # Update counters for postal codes
    mock_counters = MagicMock()
    mock_counters.nodes_created = 2
    mock_counters.relationships_created = 0
    mock_result = MagicMock()
    mock_result.consume.return_value.counters = mock_counters
    mock_transaction.run.return_value = mock_result

    loaded_count = loader.load_postal_codes(postal_codes)

    assert loaded_count == 2
    try:
        mock_session.execute_write.assert_called_once()
    except AssertionError as e:
        pytest.fail(f"execute_write was not called: {e}")

    # Get the function that was passed to execute_write
    func_passed = mock_session.execute_write.call_args[0][0]

    try:
        mock_transaction.run.assert_called_once()
    except AssertionError as e:
        pytest.fail(f"Transaction run was not called: {e}")

    call_args, call_kwargs = mock_transaction.run.call_args
    query = call_args[0]
    data = call_kwargs.get('data', [])

    assert "MERGE (:PostalCode {code: pc.code})" in query
    assert len(data) == 2
    assert data[0]["code"] == 85001
    assert data[1]["code"] == 90210


def test_load_businesses(mock_neo4j_loader):
    try:
        loader, mock_transaction, mock_session = mock_neo4j_loader
    except ValueError as e:
        pytest.fail(f"Failed to unpack mock_neo4j_loader fixture: {e}")

    businesses = [
        {"business_id": "b1", "name": "B1", "stars": 3.0, "is_open": 1},
        {"business_id": "b2", "name": "B2", "stars": 4.0, "is_open": 0}
    ]

    loaded_count = loader.load_businesses(businesses)

    assert loaded_count == 2
    try:
        mock_session.execute_write.assert_called_once()
    except AssertionError as e:
        pytest.fail(f"execute_write was not called: {e}")

    # Get the function that was passed to execute_write
    func_passed = mock_session.execute_write.call_args[0][0]

    try:
        mock_transaction.run.assert_called_once()
    except AssertionError as e:
        pytest.fail(f"Transaction run was not called: {e}")

    call_args, call_kwargs = mock_transaction.run.call_args
    query = call_args[0]
    data = call_kwargs.get('data', [])

    assert "MERGE (biz:Business {business_id: b.business_id})" in query
    assert "SET biz.name = b.name" in query
    assert len(data) == 2
    assert data[0]["business_id"] == "b1"
    assert data[0]["name"] == "B1"


def test_create_relationships_claims_state(mock_neo4j_loader):
    try:
        loader, mock_transaction, mock_session = mock_neo4j_loader
    except ValueError as e:
        pytest.fail(f"Failed to unpack mock_neo4j_loader fixture: {e}")

    # Update counters for relationship creation
    mock_counters = MagicMock()
    mock_counters.nodes_created = 0
    mock_counters.relationships_created = 1
    mock_result = MagicMock()
    mock_result.consume.return_value.counters = mock_counters
    mock_transaction.run.return_value = mock_result

    relationships = [
        {
            "from_node_type": "City", "from_node_id_prop": "name", "from_node_id_value": "Phoenix",
            "from_node_id_aux_prop": "state_code", "from_node_id_aux_value": "AZ",
            "to_node_type": "State", "to_node_id_prop": "code", "to_node_id_value": "AZ",
            "relationship_type": "CLAIMS_STATE", "properties": {}
        }
    ]

    loaded_count = loader.create_relationships(relationships)

    # For relationship creation, we expect 1 relationship created
    assert loaded_count == 1
    try:
        mock_session.execute_write.assert_called_once()
    except AssertionError as e:
        pytest.fail(f"execute_write was not called: {e}")

    # Get the function that was passed to execute_write
    func_passed = mock_session.execute_write.call_args[0][0]

    try:
        mock_transaction.run.assert_called_once()
    except AssertionError as e:
        pytest.fail(f"Transaction run was not called: {e}")

    call_args, call_kwargs = mock_transaction.run.call_args
    query = call_args[0]
    data = call_kwargs.get('data', [])

    assert "MERGE (c)-[:CLAIMS_STATE]->(s)" in query
    assert data[0]["from_node_id_value"] == "Phoenix"
    assert data[0]["from_node_id_aux_value"] == "AZ"


def test_create_relationships_located_near(mock_neo4j_loader):
    try:
        loader, mock_transaction, mock_session = mock_neo4j_loader
    except ValueError as e:
        pytest.fail(f"Failed to unpack mock_neo4j_loader fixture: {e}")

    # Update counters for relationship creation
    mock_counters = MagicMock()
    mock_counters.nodes_created = 0
    mock_counters.relationships_created = 1
    mock_result = MagicMock()
    mock_result.consume.return_value.counters = mock_counters
    mock_transaction.run.return_value = mock_result

    relationships = [
        {
            "from_node_type": "Business", "from_node_id_prop": "business_id", "from_node_id_value": "b1",
            "to_node_type": "City", "to_node_id_prop": "name", "to_node_id_value": "Phoenix",
            "to_node_id_aux_prop": "state_code", "to_node_id_aux_value": "AZ",
            "relationship_type": "LOCATED_NEAR", "properties": {"latitude": 33.1, "longitude": -112.1}
        }
    ]

    loaded_count = loader.create_relationships(relationships)

    assert loaded_count == 1
    try:
        mock_session.execute_write.assert_called_once()
    except AssertionError as e:
        pytest.fail(f"execute_write was not called: {e}")

    # Get the function that was passed to execute_write
    func_passed = mock_session.execute_write.call_args[0][0]

    try:
        mock_transaction.run.assert_called_once()
    except AssertionError as e:
        pytest.fail(f"Transaction run was not called: {e}")

    call_args, call_kwargs = mock_transaction.run.call_args
    query = call_args[0]
    data = call_kwargs.get('data', [])

    assert "MERGE (b)-[rel:LOCATED_NEAR]->(c)" in query
    assert "SET rel.latitude = r.properties['latitude']" in query
    assert data[0]["from_node_id_value"] == "b1"
    assert data[0]["properties"]["latitude"] == 33.1


def test_create_relationships_claims_postal_code(mock_neo4j_loader):
    try:
        loader, mock_transaction, mock_session = mock_neo4j_loader
    except ValueError as e:
        pytest.fail(f"Failed to unpack mock_neo4j_loader fixture: {e}")

    # Update counters for relationship creation
    mock_counters = MagicMock()
    mock_counters.nodes_created = 0
    mock_counters.relationships_created = 1
    mock_result = MagicMock()
    mock_result.consume.return_value.counters = mock_counters
    mock_transaction.run.return_value = mock_result

    relationships = [
        {
            "from_node_type": "Business", "from_node_id_prop": "business_id", "from_node_id_value": "b1",
            "to_node_type": "PostalCode", "to_node_id_prop": "code", "to_node_id_value": 85001,
            "relationship_type": "CLAIMS_POSTAL_CODE", "properties": {}
        }
    ]

    loaded_count = loader.create_relationships(relationships)

    assert loaded_count == 1
    try:
        mock_session.execute_write.assert_called_once()
    except AssertionError as e:
        pytest.fail(f"execute_write was not called: {e}")

    # Get the function that was passed to execute_write
    func_passed = mock_session.execute_write.call_args[0][0]

    try:
        mock_transaction.run.assert_called_once()
    except AssertionError as e:
        pytest.fail(f"Transaction run was not called: {e}")

    call_args, call_kwargs = mock_transaction.run.call_args
    query = call_args[0]
    data = call_kwargs.get('data', [])

    assert "MERGE (b)-[:CLAIMS_POSTAL_CODE]->(p)" in query
    assert data[0]["from_node_id_value"] == "b1"
    assert data[0]["to_node_id_value"] == 85001