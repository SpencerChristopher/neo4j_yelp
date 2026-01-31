import pytest
import logging
from src.loader import Neo4jLoader
from src.settings import settings
from neo4j.exceptions import ServiceUnavailable, ClientError

logger = logging.getLogger(__name__)

# Mark all tests in this module as integration and neo4j
pytestmark = [pytest.mark.integration, pytest.mark.neo4j]

class TestNeo4jConnectionAndState:
    def test_neo4j_connection_authentication_and_state(self, neo4j_loader: Neo4jLoader):
        """
        Tests the Neo4j connection, user authentication, and initial database state.
        This test uses the neo4j_loader fixture which ensures:
        1. The Neo4j container is up and running.
        2. The loader is initialized, connected, and verifies connectivity upon instantiation.
           This implicitly checks server finding and basic connection.
        """
        logger.info("Starting test_neo4j_connection_authentication_and_state")
        try:
            # --- Test Connection & Authentication (Implicitly done by neo4j_loader fixture) ---
            # If neo4j_loader is successfully initialized, it means:
            # - The driver connected to the server.
            # - Authentication with NEO4J_USER and NEO4J_PASSWORD succeeded.
            # - The custom IPv4 resolver worked.
            # The successful initialization of neo4j_loader implies connectivity and authentication.
            assert neo4j_loader.driver is not None
            logger.info("Neo4j driver successfully connected and authenticated.")

            # --- Check User (Implicitly handled by successful connection and authentication) ---
            # If the neo4j_loader initialized successfully, it means authentication passed.
            # We can add a simple query to ensure the session is active, if needed,
            # but dbms.security.getCurrentUser() is not available in Community Edition.
            logger.info(f"Connected to Neo4j. Assumed user: {settings.NEO4J_USER}")

            # --- Check Database State: Constraints ---
            # Constraints are created during loader initialization, so we verify them.
            try:
                with neo4j_loader.driver.session() as session:
                    constraints_count = session.run("SHOW CONSTRAINTS YIELD name RETURN count(name)").single().value()
                    logger.info(f"Number of constraints found in DB: {constraints_count}")
                    # We expect at least one constraint (e.g., for Business ID) from initial setup
                    assert constraints_count >= 1
                    logger.info("Constraints check passed.")
            except Exception as e:
                logger.error(f"Failed to check constraints: {e}", exc_info=True)
                pytest.fail(f"Could not check constraints: {e}")

            # --- Check Database State: Indexes ---
            # Indexes are also created during loader initialization
            try:
                with neo4j_loader.driver.session() as session:
                    indexes_count = session.run("SHOW INDEXES YIELD name RETURN count(name)").single().value()
                    logger.info(f"Number of indexes found in DB: {indexes_count}")
                    # Expect at least one index (excluding constraint indexes if they are not separate)
                    assert indexes_count >= 1
                    logger.info("Indexes check passed.")
            except Exception as e:
                logger.error(f"Failed to check indexes: {e}", exc_info=True)
                pytest.fail(f"Could not check indexes: {e}")

            # --- Check Database State: Node and Relationship Counts (should be 0 on clean start) ---
            try:
                with neo4j_loader.driver.session() as session:
                    nodes_count = session.run("MATCH (n) RETURN count(n)").single().value()
                    rels_count = session.run("MATCH ()-[r]->() RETURN count(r)").single().value()
                    logger.info(f"Initial DB state: Nodes={nodes_count}, Relationships={rels_count}")
                    assert nodes_count == 0, "Expected 0 nodes on a clean database start"
                    assert rels_count == 0, "Expected 0 relationships on a clean database start"
                    logger.info("Initial node and relationship counts check passed.")
            except Exception as e:
                logger.error(f"Failed to check node/relationship counts: {e}", exc_info=True)
                pytest.fail(f"Could not check node/relationship counts: {e}")

            logger.info("Finished test_neo4j_connection_authentication_and_state successfully.")
        finally:
            pass
