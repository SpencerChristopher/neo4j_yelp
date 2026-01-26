# test_pipeline.py - REAL TEST EXAMPLE
from winreg import error

import pytest
from unittest.mock import Mock, patch

try:
    from src.pipeline import run_pipeline, _write_dead_letters
    from src.loader import Neo4jLoader
except ImportError as e:  # Removed the parentheses around 'e'
    print(f"Import failed: {e}")
    raise # Re-raise the exception to make the test fail explicitly

import json
import tempfile
import os


def test_write_dead_letters(monkeypatch):
    """Test dead letter queue functionality"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl') as f:
        temp_file = f.name

    try:
        # Test with validation errors
        records = [{
            "row_number": 1,
            "entity": "Business",
            "record": {"business_id": "test"},
            "errors": [{"type": "missing_field", "msg": "Missing state"}],
            "business_id": "test"
        }]

        # Use monkeypatch fixture
        monkeypatch.setattr('src.settings.DEAD_LETTER_FILE', temp_file)

        _write_dead_letters(records)

        # Verify file was written
        with open(temp_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["entity"] == "Business"
    finally:
        os.unlink(temp_file)


def test_pipeline_with_mocks():
    """Test pipeline with mocked dependencies"""
    with patch('src.pipeline.pd.read_csv') as mock_read_csv, \
            patch('src.pipeline.Neo4jLoader') as mock_loader_class:
        # Setup mock loader
        mock_loader = Mock()
        mock_loader.load_states.return_value = (1, []) # Mock return values for methods
        mock_loader.load_cities.return_value = (1, [])
        mock_loader.load_postal_codes.return_value = (1, [])
        mock_loader.load_businesses.return_value = (1, [])
        mock_loader.load_users.return_value = (1, [])
        mock_loader.load_categories.return_value = (1, [])
        mock_loader.load_reviews.return_value = (1, [])
        mock_loader.create_relationships.return_value = (1, []) # This is the crucial one
        mock_loader_class.return_value.__enter__.return_value = mock_loader

        # Setup mock CSV data
        mock_data = {
            'business_id': ['test1', 'test2'],
            'name': ['Test Business 1', 'Test Business 2'],
            'state': ['CA', 'CA'],
            'city': ['San Francisco', 'San Francisco'],
            'postal_code': ['94105', '94105'],
            'latitude': [37.7749, 37.7749],
            'longitude': [-122.4194, -122.4194],
            'stars': [4.5, 3.5],
            'review_count': [100, 50],
            'is_open': [1, 0]
        }

        # Create mock DataFrame
        import pandas as pd
        mock_df = pd.DataFrame(mock_data)
        mock_read_csv.return_value = [mock_df]  # Returns list for chunks

        # Run pipeline with max_batches=1
        run_pipeline(max_batches=1)

        # Verify loader methods were called
        assert mock_loader.load_businesses.called
        assert mock_loader.create_relationships.called


def test_pipeline_error_handling():
    """Test pipeline error handling"""
    with patch('src.pipeline.pd.read_csv') as mock_read_csv, \
            patch('src.pipeline.Neo4jLoader') as mock_loader_class, \
            patch('src.pipeline.validate_business_data') as mock_validate:
        # Setup mocks
        mock_loader = Mock()
        mock_loader_class.return_value.__enter__.return_value = mock_loader

        # Mock validation to return invalid records
        mock_validate.return_value = ([], [{
            "row_number": 1,
            "entity": "Business",
            "record": {"invalid": "data"},
            "errors": [{"type": "validation_error", "msg": "Missing state"}]
        }])

        # Mock empty DataFrame
        import pandas as pd
        mock_read_csv.return_value = [pd.DataFrame()]

        # Run pipeline - should handle errors gracefully
        run_pipeline(max_batches=1)

        # Verify dead letters would be written
        # (Would need to mock _write_dead_letters to verify)


@pytest.mark.integration
@pytest.mark.neo4j
def test_run_pipeline_small_batch(neo4j_loader, monkeypatch):
    """
    End-to-end integration test for run_pipeline with a small batch of test data.
    Verifies node and relationship counts in Neo4j.
    """
    # Monkeypatch DATA_DIR to point to the test data
    test_data_path = os.path.join(os.path.dirname(__file__), 'data')
    monkeypatch.setattr('src.settings.DATA_DIR', test_data_path)
    monkeypatch.setattr('src.settings.BUSINESS_CSV', 'test.business_small.csv')
    monkeypatch.setattr('src.settings.USER_CSV', 'test.user_small.csv')
    monkeypatch.setattr('src.settings.CATEGORY_CSV', 'test.business_categories_small.csv')
    monkeypatch.setattr('src.settings.REVIEW_CSV', 'test.review_small.csv')
    monkeypatch.setattr('src.settings.FRIEND_CSV', 'test.user_friendship.csv')

    # Ensure a clean database (neo4j_loader fixture does this automatically)
    # The fixture also yields a connected Neo4jLoader instance.

    # Run the pipeline with a small batch
    run_pipeline(max_batches=1) # Process only the first chunk/batch

    # Verify data in Neo4j
    with neo4j_loader.driver.session() as session:
        # Verify node counts for basic entities
        assert session.run("MATCH (b:Business) RETURN count(b)").single().value == 1 # 1 business in 1st batch of test data
        assert session.run("MATCH (u:User) RETURN count(u)").single().value == 1     # 1 user in 1st batch of test data
        assert session.run("MATCH (r:Review) RETURN count(r)").single().value == 1   # 1 review in 1st batch of test data
        assert session.run("MATCH (c:Category) RETURN count(c)").single().value == 1 # A category from the test data
        assert session.run("MATCH (s:State) RETURN count(s)").single().value == 1    # A state from the test data
        assert session.run("MATCH (cy:City) RETURN count(cy)").single().value == 1   # A city from the test data
        assert session.run("MATCH (pc:PostalCode) RETURN count(pc)").single().value == 1 # A postal code from the test data

        # Verify relationship counts (from small batch of business/user/review)
        assert session.run("MATCH (:User)-[:WROTE]->(:Review) RETURN count(*)").single().value == 1
        assert session.run("MATCH (:Review)-[:OF]->(:Business) RETURN count(*)").single().value == 1
        assert session.run("MATCH (:Business)-[:CLAIMS_STATE]->(:State) RETURN count(*)").single().value == 1
        assert session.run("MATCH (:Business)-[:LOCATED_NEAR]->(:City) RETURN count(*)").single().value == 1
        assert session.run("MATCH (:City)-[:CLAIMS_STATE]->(:State) RETURN count(*)").single().value == 1
        assert session.run("MATCH (:Business)-[:CLAIMS_POSTAL_CODE]->(:PostalCode) RETURN count(*)").single().value == 1
        assert session.run("MATCH (:Business)-[:CLAIMS_CATEGORY]->(:Category) RETURN count(*)").single().value == 1


def test_neo4j_loader_import_failure_handling(monkeypatch):
    """
    Test that an ImportError during Neo4jLoader initialization within run_pipeline
    is correctly propagated, confirming the fix for the unconditional pytest.fail.
    """
    # Simulate an ImportError when Neo4jLoader's constructor is called
    monkeypatch.setattr('src.loader.Neo4jLoader.__init__',
                        Mock(side_effect=ImportError("Mocked Neo4jLoader init failure")))
    # Also mock the settings to prevent actual connection attempts by the Loader if __init__ is bypassed
    monkeypatch.setattr('src.settings.NEO4J_URI', 'mock_uri')
    monkeypatch.setattr('src.settings.NEO4J_USER', 'mock_user')
    monkeypatch.setattr('src.settings.NEO4J_PASSWORD', 'mock_password')

    with pytest.raises(ImportError, match="Mocked Neo4jLoader init failure"):
        from src.pipeline import run_pipeline # Re-import to ensure fresh module state if possible
        run_pipeline(max_batches=1)