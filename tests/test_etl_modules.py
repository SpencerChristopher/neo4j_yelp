import pytest
from pydantic import ValidationError
from src.models import CanonicalCityState, City, State, PostalCode, Business, Location
from src.validator import validate_business_data, validate_canonical_city_state_data
from src.normalizer import normalize_business_data, normalize_canonical_city_state_data
from src.loader import Neo4jLoader, load_business_data_to_neo4j, load_canonical_city_state_data_to_neo4j
import os
import pandas as pd
from unittest.mock import MagicMock, patch

# --- Fixtures (will add more as needed) ---

@pytest.fixture
def mock_business_raw_data():
    return [
        {"business_id": "b1", "name": "Test Business 1", "city": "phoenix", "state": "az", "postal_code": 85001, "latitude": 33.1, "longitude": -112.1, "stars": 3.5, "review_count": 10, "is_open": 1},
        {"business_id": "b2", "name": "Test Business 2", "city": "Scottsdale", "state": "AZ", "postal_code": 85250, "latitude": 33.2, "longitude": -112.2, "stars": 4.0, "review_count": 20, "is_open": 0},
        {"business_id": "b3", "name": "No City Or Postal", "city": None, "state": "CA", "postal_code": None, "latitude": 34.0, "longitude": -118.0, "stars": 3.0, "review_count": 5, "is_open": 1}, # Should fail validation
        {"business_id": "b4", "name": "Invalid State", "city": "Reno", "state": "NV", "postal_code": 89501, "latitude": 39.5, "longitude": -119.8, "stars": 4.5, "review_count": 15, "is_open": 1}, # State now "NV" for consistency
        {"business_id": "b5", "name": "Missing State", "city": "Las Vegas", "state": None, "postal_code": 89101, "latitude": 36.1, "longitude": -115.1, "stars": 2.5, "review_count": 8, "is_open": 1}, # Should fail validation
        {"business_id": "b6", "name": "Invalid Postal", "city": "Bad", "state": "AZ", "postal_code": 999999, "latitude": 33.1, "longitude": -112.1, "stars": 3.5, "review_count": 10, "is_open": 1}, # Should fail validation
        {"business_id": "b7", "name": "Good Business", "city": "Phoenix", "state": "AZ", "postal_code": 85001, "latitude": 33.1, "longitude": -112.1, "stars": 3.5, "review_count": 10, "is_open": 1},
    ]

@pytest.fixture
def mock_canonical_city_state_raw_data():
    return [
        {"city": "phoenix", "state_code": "az"},
        {"city": "Scottsdale", "state_code": "AZ"},
        {"city": "las vegas", "state_code": "nv"},
        {"city": "New York", "state_code": "NY"},
        {"city": "Invalid State Code", "state_code": "ABC"}, # Invalid
        {"city": None, "state_code": "CA"}, # Invalid - city missing
        {"city": "Los Angeles", "state_code": None}, # Invalid - state_code missing
        {"city": "Too Long State Code", "state_code": "LONG"}, # Invalid - state_code too long
        {"city": "Short State Code", "state_code": "S"}, # Invalid - state_code too short
        {"city": "Numbered State", "state_code": "A1"}, # Invalid - pattern mismatch
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
    assert CanonicalCityState(city="Anytown", state_code="az").state_code == "AZ" # This should pass due to normalization

    with pytest.raises(ValidationError) as exc_info:
        CanonicalCityState(city="Anytown", state_code="A1") # Contains non-alpha, still invalid
    assert "string_pattern_mismatch" in str(exc_info.value)

def test_canonical_city_state_missing_fields():
    with pytest.raises(ValidationError):
        CanonicalCityState(city="Missing State") # Missing state_code

    with pytest.raises(ValidationError):
        CanonicalCityState(state_code="CA") # Missing city

    with pytest.raises(ValidationError):
        CanonicalCityState() # Missing both

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
    assert {r["original_record"]["business_id"] for r in invalid_records} == {"b3", "b5", "b6"}
    assert all("error" in rec for rec in invalid_records)

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
    invalid_city_names = {r["original_record"]["city"] for r in invalid_records if r["original_record"]["city"] is not None}
    invalid_state_codes = {r["original_record"]["state_code"] for r in invalid_records if r["original_record"]["state_code"] is not None}
    
    assert invalid_city_names == {"Invalid State Code", "Too Long State Code", "Short State Code", "Numbered State", "Los Angeles"}
    assert invalid_state_codes == {"ABC", "LONG", "S", "A1", "CA"} # CA is here because its city is None
    assert any(rec["original_record"]["city"] is None for rec in invalid_records) # Checks for {"city": None, "state_code": "CA"}
    assert any(rec["original_record"]["state_code"] is None for rec in invalid_records) # Checks for {"city": "Los Angeles", "state_code": None}


# --- Tests for src/normalizer.py ---

def test_normalize_business_data(mock_business_raw_data):
    valid_businesses, _ = validate_business_data(mock_business_raw_data)
    
    (
        normalized_businesses,
        canonical_cities,
        canonical_states,
        canonical_postal_codes,
        relationships
    ) = normalize_business_data(valid_businesses)

    # Test normalized_businesses
    assert len(normalized_businesses) == 4
    assert {b["business_id"] for b in normalized_businesses} == {"b1", "b2", "b4", "b7"}
    assert all("city" not in b and "state" not in b and "postal_code" not in b for b in normalized_businesses)
    assert all("stars" in b and "is_open" in b and "name" in b for b in normalized_businesses)

    # Test canonical_states
    assert len(canonical_states) == 2 
    assert {s.code for s in canonical_states} == {"AZ", "NV"} # 'nevada' normalized to 'NV' in Pydantic model

    # Test canonical_cities
    assert len(canonical_cities) == 3 
    assert {f"{c.name}-{c.state_code}" for c in canonical_cities} == {"Phoenix-AZ", "Scottsdale-AZ", "Reno-NV"}

    # Test canonical_postal_codes
    assert len(canonical_postal_codes) == 3 
    assert {pc.code for pc in canonical_postal_codes} == {85001, 85250, 89501}

    # Test relationships
    # The normalize_business_data function correctly generates 12 relationships for the given valid businesses.
    assert len(relationships) == 12 

def test_normalize_canonical_city_state_data(mock_canonical_city_state_raw_data):
    valid_cs, _ = validate_canonical_city_state_data(mock_canonical_city_state_raw_data)

    canonical_cities, canonical_states, relationships = normalize_canonical_city_state_data(valid_cs)

    # Test canonical_states
    assert len(canonical_states) == 3 
    assert {s.code for s in canonical_states} == {"AZ", "NV", "NY"}

    # Test canonical_cities
    assert len(canonical_cities) == 4 
    assert {f"{c.name}-{c.state_code}" for c in canonical_cities} == {"Phoenix-AZ", "Scottsdale-AZ", "Las Vegas-NV", "New York-NY"}

    # Test relationships (CLAIMS_STATE)
    assert len(relationships) == 4 
    claims_state_rels = [r for r in relationships if r["relationship_type"] == "CLAIMS_STATE"]
    assert len(claims_state_rels) == 4
    
    # Check a specific CLAIMS_STATE relationship
    las_vegas_rel = next(r for r in claims_state_rels if r["from_node_id_value"] == "Las Vegas")
    assert las_vegas_rel["from_node_id_aux_value"] == "NV"
    assert las_vegas_rel["to_node_id_value"] == "NV"

# --- Tests for src/loader.py ---

# Fixture to mock the Neo4j driver, session, and transaction for all loader tests
@pytest.fixture
def mock_neo4j_loader(monkeypatch):
    # Mock the driver itself and its methods to prevent actual DB connection during tests
    mock_driver = MagicMock()
    mock_session = MagicMock()
    
    # Mock the transaction object itself, ensuring it has a mock 'run' method and 'consume'
    mock_transaction = MagicMock()
    mock_tx_run_result = MagicMock()
    mock_tx_run_result.consume.return_value.counters.nodes_created = 1
    mock_tx_run_result.consume.return_value.counters.relationships_created = 1
    mock_transaction.run.return_value = mock_tx_run_result # Make run return the mock result

    # Configure session.write_transaction to call the provided function with the transaction mock
    # The lambda receives the transaction object (mock_transaction) and passes it to the actual function
    mock_session.write_transaction.side_effect = lambda func, *args, **kwargs: func(mock_transaction, *args, **kwargs)
    
    # Configure the driver to return the session mock in a context manager
    mock_driver.return_value.session.return_value.__enter__.return_value = mock_session
    
    # Mock verify_connectivity to do nothing, preventing actual connection attempt during init
    mock_driver.return_value.verify_connectivity.return_value = None

    # Patch neo4j.GraphDatabase.driver to return our mocked driver instance
    monkeypatch.setattr("neo4j.GraphDatabase.driver", lambda *args, **kwargs: mock_driver)
    
    # Initialize Neo4jLoader, which will now use the mocked driver
    loader = Neo4jLoader("bolt://localhost:7687", "neo4j", "password")
    
    # Yield the loader AND the mock_transaction object for assertions
    yield loader, mock_transaction 
    loader.close() # Ensure close is called

def test_neo4j_loader_init_success(mock_neo4j_loader):
    # This test verifies that the loader initializes without error when the driver is mocked.
    # The mocked verify_connectivity prevents actual connection errors.
    loader, mock_transaction = mock_neo4j_loader # Unpack loader and mock_transaction
    assert loader.driver is not None
    # Verify that verify_connectivity was called on the mocked driver
    loader.driver.verify_connectivity.assert_called_once() 

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
    loader, mock_transaction = mock_neo4j_loader # Unpack loader and mock_transaction
    states = [State(code="AZ"), State(code="CA")]
    loaded_count = loader.load_states(states)
    
    assert loaded_count == 2
    # Verify the transaction was run with the correct query and data
    # Access the session and write_transaction from the mocked driver instance
    mock_session_context = loader.driver.session.return_value.__enter__.return_value
    mock_session_context.write_transaction.assert_called_once()
    
    # Assert on the mocked transaction object that was passed to write_transaction's lambda
    # The lambda 'func' receives the transaction object, so we assert on that object.
    mock_transaction_passed_to_lambda = mock_session_context.write_transaction.call_args[0][0]
    mock_transaction_passed_to_lambda.run.assert_called_once()
    
    tx_run_call_args, tx_run_call_kwargs = mock_transaction_passed_to_lambda.run.call_args
    assert "MERGE (s:State {code: state_props.code})" in tx_run_call_args[0]
    assert len(tx_run_call_kwargs['data']) == 2
    assert {"code": "AZ"} in tx_run_call_kwargs['data']
    assert {"code": "CA"} in tx_run_call_kwargs['data']

def test_load_cities(mock_neo4j_loader):
    loader, mock_transaction = mock_neo4j_loader # Unpack loader and mock_transaction
    cities = [City(name="Phoenix", state_code="AZ"), City(name="Tucson", state_code="AZ")]
    loaded_count = loader.load_cities(cities)

    assert loaded_count == 2
    mock_session_context = loader.driver.session.return_value.__enter__.return_value
    mock_session_context.write_transaction.assert_called_once()
    mock_transaction_passed_to_lambda = mock_session_context.write_transaction.call_args[0][0]
    mock_transaction_passed_to_lambda.run.assert_called_once()
    
    tx_run_call_args, tx_run_call_kwargs = mock_transaction_passed_to_lambda.run.call_args
    assert "MERGE (c:City {name: city_props.name, state_code: city_props.state_code})" in tx_run_call_args[0]
    assert len(tx_run_call_kwargs['data']) == 2
    assert {"name": "Phoenix", "state_code": "AZ"} in tx_run_call_kwargs['data']

def test_load_postal_codes(mock_neo4j_loader):
    loader, mock_transaction = mock_neo4j_loader # Unpack loader and mock_transaction
    postal_codes = [PostalCode(code=85001), PostalCode(code=90210)]
    loaded_count = loader.load_postal_codes(postal_codes)

    assert loaded_count == 2
    mock_session_context = loader.driver.session.return_value.__enter__.return_value
    mock_session_context.write_transaction.assert_called_once()
    mock_transaction_passed_to_lambda = mock_session_context.write_transaction.call_args[0][0]
    mock_transaction_passed_to_lambda.run.assert_called_once()
    
    tx_run_call_args, tx_run_call_kwargs = mock_transaction_passed_to_lambda.run.call_args
    assert "MERGE (pc:PostalCode {code: pc_props.code})" in tx_run_call_args[0]
    assert len(tx_run_call_kwargs['data']) == 2
    assert {"code": 85001} in tx_run_call_kwargs['data']

def test_load_businesses(mock_neo4j_loader):
    loader, mock_transaction = mock_neo4j_loader # Unpack loader and mock_transaction
    businesses = [
        {"business_id": "b1", "name": "B1", "stars": 3.0, "is_open": 1},
        {"business_id": "b2", "name": "B2", "stars": 4.0, "is_open": 0}
    ]
    loaded_count = loader.load_businesses(businesses)

    assert loaded_count == 2
    mock_session_context = loader.driver.session.return_value.__enter__.return_value
    mock_session_context.write_transaction.assert_called_once()
    mock_transaction_called_in_lambda = mock_session_context.write_transaction.call_args[0][0]
    mock_transaction_called_in_lambda.run.assert_called_once()
    
    tx_run_call_args, tx_run_call_kwargs = mock_transaction_called_in_lambda.run.call_args
    assert "MERGE (b:Business {business_id: business_props.business_id})" in tx_run_call_args[0]
    assert "SET b.name = business_props.name" in tx_run_call_args[0]
    assert len(tx_run_call_kwargs['data']) == 2
    assert {"business_id": "b1", "name": "B1", "stars": 3.0, "is_open": 1} in tx_run_call_kwargs['data']

def test_create_relationships_claims_state(mock_neo4j_loader):
    loader, mock_transaction = mock_neo4j_loader # Unpack loader and mock_transaction
    relationships = [
        {
            "from_node_type": "City", "from_node_id_prop": "name", "from_node_id_value": "Phoenix",
            "from_node_id_aux_prop": "state_code", "from_node_id_aux_value": "AZ",
            "to_node_type": "State", "to_node_id_prop": "code", "to_node_id_value": "AZ",
            "relationship_type": "CLAIMS_STATE", "properties": {}
        }
    ]
    loaded_count = loader.create_relationships(relationships)
    
    assert loaded_count == 1
    mock_session_context = loader.driver.session.return_value.__enter__.return_value
    mock_session_context.write_transaction.assert_called_once()
    # Assert on the mocked transaction object passed to the lambda
    mock_transaction_called_in_lambda = mock_session_context.write_transaction.call_args[0][0]
    mock_transaction_called_in_lambda.run.assert_called_once()
    tx_run_call_args, tx_run_call_kwargs = mock_transaction_called_in_lambda.run.call_args
    assert "MERGE (c)-[r:CLAIMS_STATE]->(s)" in tx_run_call_args[0]
    assert tx_run_call_kwargs['data'][0]["from_node_id_value"] == "Phoenix"

def test_create_relationships_located_near(mock_neo4j_loader):
    loader, mock_transaction = mock_neo4j_loader # Unpack loader and mock_transaction
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
    mock_session_context = loader.driver.session.return_value.__enter__.return_value
    mock_session_context.write_transaction.assert_called_once()
    mock_transaction_called_in_lambda = mock_session_context.write_transaction.call_args[0][0]
    mock_transaction_called_in_lambda.run.assert_called_once()
    tx_run_call_args, tx_run_call_kwargs = mock_transaction_called_in_lambda.run.call_args
    assert "MERGE (b)-[r:LOCATED_NEAR]->(c)" in tx_run_call_args[0]
    assert "SET r.latitude = rel_props.properties.latitude" in tx_run_call_args[0]
    assert tx_run_call_kwargs['data'][0]["from_node_id_value"] == "b1"
    assert tx_run_call_kwargs['data'][0]["properties"]["latitude"] == 33.1

def test_create_relationships_claims_postal_code(mock_neo4j_loader):
    loader, mock_transaction = mock_neo4j_loader # Unpack loader and mock_transaction
    relationships = [
        {
            "from_node_type": "Business", "from_node_id_prop": "business_id", "from_node_id_value": "b1",
            "to_node_type": "PostalCode", "to_node_id_prop": "code", "to_node_id_value": 85001,
            "relationship_type": "CLAIMS_POSTAL_CODE", "properties": {}
        }
    ]
    loaded_count = loader.create_relationships(relationships)

    assert loaded_count == 1
    mock_session_context = loader.driver.session.return_value.__enter__.return_value
    mock_session_context.write_transaction.assert_called_once()
    mock_transaction_called_in_lambda = mock_session_context.write_transaction.call_args[0][0]
    mock_transaction_called_in_lambda.run.assert_called_once()
    tx_run_call_args, tx_run_call_kwargs = mock_transaction_called_in_lambda.run.call_args
    assert "MERGE (b)-[r:CLAIMS_POSTAL_CODE]->(pc)" in tx_run_call_args[0]
    assert tx_run_call_kwargs['data'][0]["from_node_id_value"] == "b1"

# --- Updated tests for loading functions ---

def test_load_canonical_city_state_data_to_neo4j(mock_neo4j_loader):
    loader, mock_transaction = mock_neo4j_loader # Unpack loader and mock_transaction
    cities = [City(name="Phoenix", state_code="AZ")]
    states = [State(code="AZ")]
    relationships = [
        {
            "from_node_type": "City", "from_node_id_prop": "name", "from_node_id_value": "Phoenix",
            "from_node_id_aux_prop": "state_code", "from_node_id_aux_value": "AZ",
            "to_node_type": "State", "to_node_id_prop": "code", "to_node_id_value": "AZ",
            "relationship_type": "CLAIMS_STATE", "properties": {}
        }
    ]

    # Mock the internal loader methods called by load_canonical_city_state_data_to_neo4j
    with patch.object(loader, 'load_states') as mock_load_states, \
         patch.object(loader, 'load_cities') as mock_load_cities, \
         patch.object(loader, 'create_relationships') as mock_create_relationships:
        
        mock_load_states.return_value = 1 # Simulate loading one state
        mock_load_cities.return_value = 1 # Simulate loading one city
        mock_create_relationships.return_value = 1 # Simulate creating one relationship

        total_nodes, total_rels = load_canonical_city_state_data_to_neo4j(cities, states, relationships)

        assert total_nodes == 2
        assert total_rels == 1

        loader.load_states.assert_called_once_with(states)
        loader.load_cities.assert_called_once_with(cities)
        loader.create_relationships.assert_called_once_with(relationships)


def test_load_business_data_to_neo4j(mock_neo4j_loader):
    loader, mock_transaction = mock_neo4j_loader # Unpack loader and mock_transaction
    businesses = [{"business_id": "b1", "name": "B1", "stars": 3.0, "is_open": 1}]
    cities = [City(name="Phoenix", state_code="AZ")]
    states = [State(code="AZ")]
    postal_codes = [PostalCode(code=85001)]
    relationships = [
        {
            "from_node_type": "Business", "from_node_id_prop": "business_id", "from_node_id_value": "b1",
            "to_node_type": "City", "to_node_id_prop": "name", "to_node_id_value": "Phoenix",
            "to_node_id_aux_prop": "state_code", "to_node_id_aux_value": "AZ",
            "relationship_type": "LOCATED_NEAR", "properties": {"latitude": 33.1, "longitude": -112.1}
        }
    ]

    with patch.object(loader, 'load_states') as mock_load_states, \
         patch.object(loader, 'load_cities') as mock_load_cities, \
         patch.object(loader, 'load_postal_codes') as mock_load_postal_codes, \
         patch.object(loader, 'load_businesses') as mock_load_businesses, \
         patch.object(loader, 'create_relationships') as mock_create_relationships:
        
        mock_load_states.return_value = 1 # Simulate loading one state
        mock_load_cities.return_value = 1 # Simulate loading one city
        mock_load_postal_codes.return_value = 1 # Simulate loading one postal code
        mock_load_businesses.return_value = 1 # Simulate loading one business
        mock_create_relationships.return_value = 1 # Simulate creating one relationship

        total_nodes, total_rels = load_business_data_to_neo4j(businesses, cities, states, postal_codes, relationships)

        assert total_nodes == 4 
        assert total_rels == 1 

        loader.load_states.assert_called_once_with(states)
        loader.load_cities.assert_called_once_with(cities)
        loader.load_postal_codes.assert_called_once_with(postal_codes)
        loader.load_businesses.assert_called_once_with(businesses)
        loader.create_relationships.assert_called_once_with(relationships)
