from unittest.mock import MagicMock

from src.integrity_checks import verify_data_integrity


def _normalize(s: str) -> str:
    return "".join(s.split()).lower()


def test_verify_data_integrity_relationship_count_query_is_valid():
    """
    Ensure the relationship count query binds the relationship variable.
    This test should fail if the query uses an unbound 'r'.
    """
    mock_session = MagicMock()
    mock_session.run.return_value.single.return_value = [0]

    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    mock_loader = MagicMock()
    mock_loader.driver = mock_driver

    verify_data_integrity(mock_loader)

    queries = [call.args[0] for call in mock_session.run.call_args_list]
    normalized_queries = [_normalize(q) for q in queries]

    expected = _normalize("MATCH ()-[r]-() RETURN count(r) as total_rels")
    assert expected in normalized_queries, "Relationship count query should bind r in the MATCH pattern."
