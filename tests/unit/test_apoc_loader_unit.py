import pytest
from unittest.mock import MagicMock, patch
from src.loader import Neo4jLoader


@pytest.fixture
def neo4j_loader_mocked_driver():
    """Neo4jLoader instance with its driver attribute directly mocked."""
    mock_session = MagicMock()
    mock_driver = MagicMock()
    
    # Configure mock_driver to return a context manager mock that yields our mock_session
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_driver.session.return_value.__exit__.return_value = False # Propagate exceptions

    # Create a real Neo4jLoader instance, then replace its driver attribute with our mock
    # Patching 'src.loader.GraphDatabase.driver' to prevent actual connection attempt during init
    with patch('src.loader.GraphDatabase.driver'):
        # Temporarily disable _create_constraints_and_indexes during __init__
        with patch.object(Neo4jLoader, '_create_constraints_and_indexes', MagicMock()):
            loader = Neo4jLoader()

    # Now, replace the loader's driver with our mock_driver
    loader.driver = mock_driver
    
    yield loader, mock_session

class TestNeo4jLoaderApocFriends:
    """Unit tests for the APOC-based friend relationship loader."""

    def test_load_friend_relationships_apoc_generates_correct_query(self, neo4j_loader_mocked_driver):
        """
        Verifies that load_friend_relationships_apoc constructs and executes the correct Cypher query.
        """
        loader, mock_session = neo4j_loader_mocked_driver
        
        csv_file_name = "user_friendship.csv"
        
        # Configure mock_session.run().single() for this specific test
        mock_run_return_value = MagicMock() # Create a mock for what session.run() returns
        mock_run_return_value.single.return_value = {
            "batches": 10,
            "total": 50000,
            "errorMessages": []
        }
        mock_session.run.return_value = mock_run_return_value

        batches, total_rels, errors = loader.load_friend_relationships_apoc(csv_file_name)

        # Assert session.run was called once and capture the query
        mock_session.run.assert_called_once()
        actual_query = mock_session.run.call_args[0][0]
        
        # --- REVISED ASSERTIONS: Robust, whitespace-agnostic checks for key components ---
        normalized_actual_query = "".join(actual_query.split()).lower()

        assert "callapoc.periodic.iterate" in normalized_actual_query
        assert f"loadcsvwithheadersfrom'file:///{csv_file_name}'asrowreturnrow" in normalized_actual_query.lower()
        assert "match(u1:user{user_id:row.user1})" in normalized_actual_query
        assert "match(u2:user{user_id:row.user2})" in normalized_actual_query
        assert "merge(u1)-[:friends_with]->(u2)" in normalized_actual_query
        assert "{batchsize:10000,parallel:true,iteratelist:true,retries:5}" in normalized_actual_query
        assert "yieldbatches,total,errormessagesreturnbatches,total,errormessages" in normalized_actual_query
        # --- END REVISED ASSERTIONS ---

        assert batches == 10
        assert total_rels == 50000
        assert errors == []

    def test_load_friend_relationships_apoc_handles_apoc_errors(self, neo4j_loader_mocked_driver):
        """
        Verifies that errors reported by apoc.periodic.iterate are logged and returned.
        """
        loader, mock_session = neo4j_loader_mocked_driver
        
        csv_file_name = "user_friendship.csv"
        apoc_error_message = ["Failed to merge some relationships due to missing nodes."]
        
        # Configure mock_session.run().single() for this specific test
        mock_run_return_value = MagicMock()
        mock_run_return_value.single.return_value = {
            "batches": 5,
            "total": 20000,
            "errorMessages": apoc_error_message
        }
        mock_session.run.return_value = mock_run_return_value

        with patch('src.loader.logger.error') as mock_logger_error:
            batches, total_rels, errors = loader.load_friend_relationships_apoc(csv_file_name)
            
            # The log message will contain the actual list, not a MagicMock
            mock_logger_error.assert_called_once_with(f"APOC periodic iterate reported errors for {csv_file_name}: {apoc_error_message}")
            assert batches == 5
            assert total_rels == 20000
            assert errors == apoc_error_message

    def test_load_friend_relationships_apoc_handles_exception(self, neo4j_loader_mocked_driver):
        """
        Verifies that exceptions during session.run are caught, logged, and re-raised.
        """
        loader, mock_session = neo4j_loader_mocked_driver
        
        csv_file_name = "user_friendship.csv"
        # For this test, mock_session.run should raise an exception
        mock_session.run.side_effect = Exception("Neo4j connection error")

        with patch('src.loader.logger.error') as mock_logger_error:
            with pytest.raises(Exception, match="Neo4j connection error"):
                loader.load_friend_relationships_apoc(csv_file_name)
            
            mock_logger_error.assert_called_once()
            assert "Failed server-side friend loading" in mock_logger_error.call_args[0][0]