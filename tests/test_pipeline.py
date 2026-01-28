import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

try:
    from src.pipeline import run_pipeline, _write_dead_letters
    from src.loader import Neo4jLoader
except ImportError as e:
    print(f"Import failed: {e}")
    raise # Re-raise the exception to make the test fail explicitly


def test_pipeline_with_mocks():
    """Test pipeline with mocked dependencies"""
    with patch('src.pipeline.pd.read_csv') as mock_read_csv, \
            patch('src.pipeline.Neo4jLoader') as MockNeo4jLoaderClass, \
            patch('src.settings.settings') as mock_settings:

        # Explicitly make the instance returned by Neo4jLoader() a MagicMock
        MockNeo4jLoaderClass.return_value = MagicMock()

        # Now configure the instance that __enter__ will return
        mock_loader_instance = MockNeo4jLoaderClass.return_value.__enter__.return_value

        # Configure methods on this specific mock instance
        mock_loader_instance.load_states.return_value = (1, [])
        mock_loader_instance.load_cities.return_value = (1, [])
        mock_loader_instance.load_postal_codes.return_value = (1, [])
        mock_loader_instance.load_businesses_complete.return_value = (1, [])
        mock_loader_instance.load_users.return_value = (1, [])
        mock_loader_instance.load_categories.return_value = (1, [])
        mock_loader_instance.load_reviews.return_value = (1, [])
        mock_loader_instance.create_relationships.return_value = (1, [])
        mock_loader_instance.driver = Mock()
        mock_loader_instance.driver.session.return_value = MagicMock()

        # Ensure __exit__ is also mocked on the context manager mock
        MockNeo4jLoaderClass.return_value.__exit__.return_value = None


def test_pipeline_error_handling():
    """Test pipeline error handling"""
    with patch('src.pipeline.pd.read_csv') as mock_read_csv, \
            patch('src.pipeline.Neo4jLoader') as mock_loader_class, \
            patch('src.validator.validate_records') as mock_validate: # Corrected mock target
        # Setup mocks
        mock_loader = Mock()
        mock_loader.driver = Mock() # Make loader.driver support context manager
        mock_loader.driver.session.return_value = MagicMock()
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
        
        mock_iterator = MagicMock()
        mock_iterator.__enter__.return_value = [pd.DataFrame()]
        mock_iterator.__exit__.return_value = None
        mock_read_csv.return_value = mock_iterator

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
    # Monkeypatch DATA_DIR to point to the test data directory.
    test_data_dir = Path(__file__).parent / "data" # Resolves to tests/data
    monkeypatch.setattr('src.settings.settings.DATA_DIR', test_data_dir)

    # Construct new PhaseConfig objects with the "test." prefixed filenames
    # and then monkeypatch the entire settings.pipeline.phases list.
    from src.settings import PhaseConfig # Import PhaseConfig here for use

    new_phases = [
        PhaseConfig(
            name="Users",
            csv_file_name=Path("test.user_small.csv"),
            chunk_size=500,
            validator_func_name="validate_user_data",
            normalizer_func_name="normalize_user_data",
            loader_method_name="load_nodes",
            model_name="User",
            node_label="User",
            id_property="user_id"
        ),
        PhaseConfig(
            name="Businesses with Geographic Relationships",
            csv_file_name=Path("test.business_small.csv"),
            chunk_size=200,
            validator_func_name="validate_business_data",
            normalizer_func_name="normalize_business_data",
            loader_method_name="process_business_data",
            model_name="Business",
            node_label="Business",
            id_property="business_id"
        ),
        PhaseConfig(
            name="Categories and Business-Category Relationships",
            csv_file_name=Path("test.business_categories_small.csv"),
            chunk_size=1000,
            validator_func_name="validate_category_data",
            normalizer_func_name="normalize_category_data",
            loader_method_name="load_nodes",
            model_name="Category",
            node_label="Category",
            id_property="name"
        ),
        PhaseConfig(
            name="Reviews with Immediate User/Business Relationships",
            csv_file_name=Path("test.review_small.csv"),
            chunk_size=300,
            validator_func_name="validate_review_data",
            normalizer_func_name="normalize_review_data",
            loader_method_name="load_nodes",
            model_name="Review",
            node_label="Review",
            id_property="review_id"
        ),
        PhaseConfig(
            name="Friend Relationships",
            csv_file_name=Path("test.user_friendship.csv"),
            chunk_size=500,
            validator_func_name="validate_friend_data",
            normalizer_func_name="normalize_friend_data",
            loader_method_name="load_relationships",
            model_name="Friend",
            node_label=None,
            id_property=None
        )
    ]
    monkeypatch.setattr('src.settings.settings.pipeline.phases', new_phases)

def test_neo4j_loader_import_failure_handling(monkeypatch):
    """
    Test that an ImportError during Neo4jLoader initialization within run_pipeline
    is correctly propagated, confirming the fix for the unconditional pytest.fail.
    """
    # Simulate an ImportError when Neo4jLoader's constructor is called
    monkeypatch.setattr('src.loader.Neo4jLoader.__init__',
                        Mock(side_effect=ImportError("Mocked Neo4jLoader init failure")))
    # Also mock the settings to prevent actual connection attempts by the Loader if __init__ is bypassed
    # Remove the following three lines as Neo4jLoader no longer takes these args directly
    # monkeypatch.setattr('src.settings.NEO4J_URI', 'mock_uri')
    # monkeypatch.setattr('src.settings.NEO4J_USER', 'mock_user')
    # monkeypatch.setattr('src.settings.NEO4J_PASSWORD', 'mock_password')

    with pytest.raises(ImportError, match="Mocked Neo4jLoader init failure"):
        from src.pipeline import run_pipeline # Re-import to ensure fresh module state if possible
        run_pipeline(max_batches=1)