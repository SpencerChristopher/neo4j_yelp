import pytest
from unittest.mock import MagicMock, patch
from src.loader import Neo4jLoader
from src.settings import settings


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

        friend_phase_config = next(
            (phase for phase in settings.pipeline.phases if phase.loader_method_name == "load_friends_apoc"),
            None
        )
        apoc_batch_size = friend_phase_config.chunk_size if friend_phase_config else 1000
        
        with patch.object(loader, "_run_apoc_job") as mock_run:
            mock_run.side_effect = [(5, 50000, []), (10, 50000, [])]
            batches, total_rels, errors = loader.load_friend_relationships_apoc(csv_file_name)

        # Assert submit query was called and capture the cypher
        stage_cypher = mock_run.call_args_list[0][0][1]
        merge_cypher = mock_run.call_args_list[1][0][1]

        # --- REVISED ASSERTIONS: Robust, whitespace-agnostic checks for key components ---
        normalized_stage_query = "".join(stage_cypher.split()).lower()
        normalized_merge_query = "".join(merge_cypher.split()).lower()

        assert "callapoc.periodic.iterate" in normalized_stage_query
        # Check for the LOAD CSV part and the WHERE clause separately for robustness
        expected_csv_path = settings.neo4j_file_url(csv_file_name)
        assert f"loadcsvwithheadersfrom'{expected_csv_path}'asrow" in normalized_stage_query
        assert "whererow.user1isnotnullandrow.user2isnotnullandrow.user1<>row.user2" in normalized_stage_query
        assert "returnrow" in normalized_stage_query
        assert "create(:friendshipstage{user1:row.user1,user2:row.user2})" in normalized_stage_query
        assert f"{{batchsize:{apoc_batch_size},parallel:false,iteratelist:true,retries:5}}" in normalized_stage_query

        assert "callapoc.periodic.iterate" in normalized_merge_query
        assert "match(fs:friendshipstage)returnfs" in normalized_merge_query
        assert "match(u1:user{user_id:fs.user1})" in normalized_merge_query
        assert "match(u2:user{user_id:fs.user2})" in normalized_merge_query
        assert "merge(u1)-[:friends_with]->(u2)" in normalized_merge_query
        assert "deletefs" in normalized_merge_query
        assert f"{{batchsize:{apoc_batch_size},parallel:false,iteratelist:true,retries:5}}" in normalized_merge_query
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
        
        stage_result = MagicMock()
        stage_result.single.return_value = {
            "batches": 1,
            "total": 10,
            "errorMessages": apoc_error_message
        }
        merge_result = MagicMock()
        merge_result.single.return_value = {
            "batches": 5,
            "total": 20000,
            "errorMessages": apoc_error_message
        }
        mock_session.run.side_effect = [stage_result, merge_result]

        with patch('src.loader.logger.error') as mock_logger_error:
            batches, total_rels, errors = loader.load_friend_relationships_apoc(csv_file_name, async_mode=False)
            
            # The log message will contain the actual list, not a MagicMock
            assert mock_logger_error.call_count >= 1
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
