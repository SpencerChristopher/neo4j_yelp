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
    user_csv_path = settings.DATA_DIR / settings.USER_CSV
    
    # We must use the absolute path for the Docker container to see the file
    apoc_user_import_query = f'''
        LOAD CSV WITH HEADERS FROM 'file:///{user_csv_path.as_posix()}' AS row
        MERGE (u:User {{user_id: row.user_id}})
        ON CREATE SET u.name = row.name
    '''
    with neo4j_loader.driver.session() as session:
        session.run("CREATE CONSTRAINT User_user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE")
        session.run(apoc_user_import_query)
        logger.info("Initial user nodes loaded for APOC test.")

    # Call the APOC friend loading method
    friend_csv_filename = settings.FRIEND_CSV
    neo4j_loader.load_friends_apoc(friend_csv_filename)
    logger.info(f"APOC friend loading from '{friend_csv_filename}' complete.")

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
        assert actual_rel_count == expected_friendship_count, \
            f"Expected {expected_friendship_count} relationships, found {actual_rel_count}"
        logger.info(f"FRIENDS_WITH relationship count verified: {actual_rel_count}")

        # 3. Verify a specific friendship exists
        user1 = test_data_provider['sample_friendship_user1']
        user2 = test_data_provider['sample_friendship_user2']
        friendship_exists_query = f"""
            MATCH (u1:User {{user_id: '{user1}'}})-[:FRIENDS_WITH]->(u2:User {{user_id: '{user2}'}})
            RETURN count(*) > 0 AS friendshipExists
        """
        result = session.run(friendship_exists_query).single()
        assert result and result['friendshipExists'], \
            f"Expected friendship between {user1} and {user2} was not found."
        logger.info(f"Verified specific friendship between {user1} and {user2}.")
