import pytest
from src.loader import Neo4jLoader
import subprocess
import logging
from pathlib import Path
from src.settings import settings
import pandas as pd
from tests.utils import csv_path

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
    container_user_csv_path = settings.neo4j_import_relative_path(str(settings.USER_CSV))
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
    container_friend_csv_path = "test.tiny_user_friendship.csv" # Filename only; loader builds file URL
    batches, total, errors = neo4j_loader.load_friend_relationships_apoc(container_friend_csv_path)
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
        # Only friendships where both users exist in the loaded user set should be created.
        user_ids = set()
        for chunk in pd.read_csv(csv_path(str(settings.USER_CSV)), chunksize=settings.BATCH_SIZE):
            user_ids.update(chunk["user_id"].astype(str).tolist())

        expected_friendship_count = 0
        expected_total_rows = 0
        sample_user1 = None
        sample_user2 = None
        for chunk in pd.read_csv(csv_path(str(settings.FRIEND_CSV)), chunksize=settings.BATCH_SIZE):
            expected_total_rows += len(chunk)
            valid = chunk[chunk["user1"].isin(user_ids) & chunk["user2"].isin(user_ids)]
            expected_friendship_count += len(valid)
            if sample_user1 is None and not valid.empty:
                sample_user1 = valid.iloc[0]["user1"]
                sample_user2 = valid.iloc[0]["user2"]
        rel_count_result = session.run("MATCH ()-[r:FRIENDS_WITH]->() RETURN count(r) as count").single()
        actual_rel_count = rel_count_result['count']
        assert actual_rel_count == expected_friendship_count, \
            f"Expected {expected_friendship_count} relationships, but found {actual_rel_count}"
        logger.info(f"FRIENDS_WITH relationship count verified: {actual_rel_count}")

        # APOC return should match the created relationship count when available
        if total:
            assert total == expected_total_rows, \
                f"APOC reported total {total} rows, but expected {expected_total_rows}"

        # 3. Verify a known friendship exists (if sample data is available)
        # Choose a sample friendship that is guaranteed to be within the loaded user set
        if sample_user1 is not None:
            friendship_result = session.run("""
                MATCH (u1:User {user_id: $u1})-[f:FRIENDS_WITH]->(u2:User {user_id: $u2})
                RETURN f
            """, u1=sample_user1, u2=sample_user2).single()
            assert friendship_result is not None, "Expected a sample FRIENDS_WITH relationship to exist."
        else:
            pytest.skip("Sample friendship data not available in test dataset.")


