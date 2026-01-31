import pytest
from src.loader import Neo4jLoader
import subprocess
import logging
from pathlib import Path
from src.settings import settings

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.integration, pytest.mark.neo4j]

def test_load_friends_with_apoc(neo4j_loader, neo4j_container_id, test_data_provider):
    """
    Tests loading friendships using the APOC load.
    It verifies that:
    - The expected number of User nodes are loaded.
    - The expected number of FRIENDS_WITH relationships are created.
    - A specific, known friendship from the test data exists.
    """
    logger.info("Starting APOC friendship loading test.")

    # Manually load the user nodes first, as this is a prerequisite for creating relationships
    # Use the container path for the test CSV file
    container_user_csv_path = "test_data/test.user_small.csv" # Path relative to /var/lib/neo4j/import
    apoc_user_import_query = f'''
        LOAD CSV WITH HEADERS FROM 'file:///{container_user_csv_path}' AS row
        MERGE (u:User {{user_id: row.user_id}})
        ON CREATE SET u.name = row.name
    '''
    with neo4j_loader.driver.session() as session:
        session.run("CREATE CONSTRAINT User_user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE")
        session.run(apoc_user_import_query)
        logger.info("Initial user nodes loaded for APOC test.")

        # --- NEW ASSERTION: Verify User nodes loaded correctly ---
        actual_users_loaded_count = session.run("MATCH (u:User) RETURN count(u) AS count").single()["count"]
        expected_users_in_csv = test_data_provider['user_count']
        assert actual_users_loaded_count == expected_users_in_csv, \
            f"Expected {expected_users_in_csv} users to be loaded, but found {actual_users_loaded_count}."
        logger.info(f"Verified {actual_users_loaded_count} users loaded correctly.")
        # --- END NEW ASSERTION ---

    # Call the APOC friend loading method
    # Use the container path for the test friendship CSV file
    container_friend_csv_path = "test_data/test.user_friendship.csv" # Path relative to /var/lib/neo4j/import
    neo4j_loader.load_friend_relationships_apoc(container_friend_csv_path)
    logger.info(f"APOC friend loading from '{container_friend_csv_path}' complete.")

    # Verification
    with neo4j_loader.driver.session() as session:
        # 1. Verify User node count
        expected_user_count = test_data_provider['user_count']
        user_count_result = session.run("MATCH (u:User) RETURN count(u) AS count").single()
        actual_user_count = user_count_result['count']
        assert actual_user_count == expected_user_count, \
            f"Expected {expected_user_count} users, but found {actual_user_count}."
        logger.info(f"User count verified: {actual_user_count}")

        # 2. Verify FRIENDS_WITH relationship count
        expected_friendship_count = test_data_provider['friendship_count']
        rel_count_result = session.run("MATCH ()-[r:FRIENDS_WITH]->() RETURN count(r) as count").single()
        actual_rel_count = rel_count_result['count']
        assert actual_rel_count == 24, \
            f"Expected 24 relationships, but found {actual_rel_count}"
        logger.info(f"FRIENDS_WITH relationship count verified: {actual_rel_count}")


