import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

try:
    from src.pipeline import run_pipeline as pipeline_run
    from src.loader import Neo4jLoader
except ImportError as e:
    print(f"Import failed: {e}")
    raise # Re-raise the exception to make the test fail explicitly





def test_pipeline_error_handling():
    """Test pipeline error handling: validation failures are written to dead letter."""
    # Patch dependencies
    with patch('src.pipeline.pd.read_csv') as mock_read_csv, \
            patch('src.pipeline.Neo4jLoader') as mock_loader_class, \
            patch('src.validator.validate_records') as mock_validate, \
            patch('src.pipeline.write_dead_letters') as mock_write_dead_letters, \
            patch('src.pipeline.verify_data_integrity') as mock_verify_integrity, \
            patch('src.pipeline.validate_review_counts') as mock_validate_review_counts:

        # Setup mocks for Neo4jLoader (minimal setup as it's not the focus)
        mock_loader = Mock()
        mock_loader.driver = Mock()
        mock_loader.driver.session.return_value = MagicMock()
        mock_loader_class.return_value.__enter__.return_value = mock_loader

        # Mock validation to return invalid records
        invalid_records = [{
            "row_number": 1,
            "entity": "Business",
            "record": {"invalid": "data"},
            "errors": [{"type": "validation_error", "msg": "Missing state"}]
        }]
        mock_validate.return_value = ([], invalid_records)

        # Mock empty DataFrame to avoid actual CSV reading issues
        import pandas as pd
        mock_iterator = MagicMock()
        mock_iterator.__enter__.return_value = [pd.DataFrame([{"col1": 1}])] # Non-empty DF to trigger processing
        mock_iterator.__exit__.return_value = None
        mock_read_csv.return_value = mock_iterator

        # Run pipeline with a single batch
        # We need to configure a phase that actually uses validation
        from src.settings import settings, PhaseConfig
        original_phases = settings.pipeline.phases
        original_data_dir = settings.DATA_DIR

        temp_dir = Path(tempfile.mkdtemp())
        settings.DATA_DIR = temp_dir
        (temp_dir / "mock.csv").write_text("col1\n1\n", encoding="utf-8")
        settings.pipeline.phases = [
                PhaseConfig(
                    name="Mocked Phase",
                    csv_file_name=Path("mock.csv"),
                    chunk_size=1,
                    validator_func_name="validate_user_data", # Any valid validator name
                    normalizer_func_name="normalize_user_data", # Any valid normalizer name
                    loader_method_name="load_nodes", # Ensures validation runs
                    model_name="User",
                    node_label="User",
                    id_property="user_id"
                )
            ]

        pipeline_run(max_batches=1)

        # Restore original phases
        settings.pipeline.phases = original_phases
        settings.DATA_DIR = original_data_dir

        # Assert that write_dead_letters was called with the invalid records
        mock_write_dead_letters.assert_called_once_with(
            invalid_records,
            settings.pipeline.dead_letter_max_records_per_batch
        )

        # Optionally, assert on PipelineStats if we mock it directly
        # For now, asserting on dead_letter_handler is sufficient for error handling.




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
        pipeline_run(max_batches=1)
