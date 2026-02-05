import pytest
import logging
from src.loader import Neo4jLoader
from src.settings import settings
from neo4j.exceptions import ServiceUnavailable, ClientError
from pathlib import Path
import os

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

            # --- Check Required User Uniqueness Constraint Exists ---
            try:
                with neo4j_loader.driver.session() as session:
                    # Neo4j 5.x returns constraint name and description; use description to verify target
                    result = session.run("SHOW CONSTRAINTS YIELD name, description WHERE description CONTAINS 'User' AND description CONTAINS 'user_id' RETURN count(name) AS count").single()
                    user_constraint_count = result["count"] if result else 0
                    assert user_constraint_count >= 1, "Expected a uniqueness constraint on User(user_id)."
                    logger.info("User user_id uniqueness constraint check passed.")
            except Exception as e:
                logger.error(f"Failed to check User(user_id) constraint: {e}", exc_info=True)
                pytest.fail(f"Could not verify User(user_id) uniqueness constraint: {e}")

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

    def test_apoc_procedures_available(self, neo4j_loader: Neo4jLoader):
        """
        Verifies that APOC procedures are installed, enabled, and callable.
        Crucial for apoc.periodic.iterate and LOAD CSV functionality.
        """
        logger.info("Starting test_apoc_procedures_available")
        try:
            with neo4j_loader.driver.session() as session:
                # Test a simple APOC procedure like apoc.version()
                result = session.run("RETURN apoc.version()").single()
                assert result is not None, "apoc.version() did not return a result. APOC might not be installed or enabled."
                logger.info(f"APOC version: {result.value()}. APOC procedures are available.")

                # Check if apoc.import.csv is allowed (implicitly needed for LOAD CSV FROM 'file:///')
                # This doesn't directly check the setting, but successful LOAD CSV will.
                # A more direct check would be:
                # result = session.run("CALL dbms.security.procedures() YIELD name, signature, argumentDescription, mode WHERE name = 'apoc.import.csv' RETURN mode").single()
                # assert result and result.value() == "read", "apoc.import.csv is not enabled for read access from files."

        except ClientError as e:
            if "Unknown function" in str(e) or "There is no procedure with the name `apoc.version`" in str(e):
                pytest.fail(f"APOC procedures are not installed or enabled: {e}")
            else:
                pytest.fail(f"Error checking APOC procedures: {e}")
        except Exception as e:
            pytest.fail(f"Unexpected error during APOC procedures check: {e}")
        logger.info("APOC procedures availability check passed.")


    def test_apoc_load_csv_external_resource_access(self, neo4j_loader: Neo4jLoader):
        """
        Verifies that Neo4j can access external CSV files via 'file:///' using LOAD CSV.
        This confirms the Docker volume mounts are working correctly for imports.
        """
        logger.info("Starting test_apoc_load_csv_external_resource_access")

        # Create a dummy CSV file in the mounted tests/data directory if it doesn't exist
        # This ensures the test is self-contained and doesn't rely on existing test.user_small.csv
        test_file_name = "temp_load_csv_test.csv"
        container_test_path = f"test_data/{test_file_name}" # Relative to /var/lib/neo4j/import
        
        # Get the actual host path for writing the temporary file
        project_root = Path(__file__).parent.parent.parent
        tests_data_dir = project_root / "tests" / "data"
        temp_csv_file_path = tests_data_dir / test_file_name

        try:
            # Ensure the directory exists
            tests_data_dir.mkdir(parents=True, exist_ok=True)

            # Write a simple CSV for the test
            with open(temp_csv_file_path, "w") as f:
                f.write("id,name\n")
                f.write("1,TestUser\n")

            logger.info(f"Created temporary CSV for LOAD CSV test at host path: {temp_csv_file_path}")

            with neo4j_loader.driver.session() as session:
                # Attempt to load the CSV using the container path
                query = f"""
                LOAD CSV WITH HEADERS FROM 'file:///{container_test_path}' AS row
                RETURN row.id, row.name
                """
                result = session.run(query).single()

                assert result is not None, "LOAD CSV from external resource failed to return any data."
                assert result["row.id"] == "1", "Loaded data 'id' mismatch."
                assert result["row.name"] == "TestUser", "Loaded data 'name' mismatch."

                logger.info(f"Successfully loaded data from '{container_test_path}'. External resource access confirmed.")

        except ClientError as e:
            if "Couldn't load the external resource" in str(e):
                pytest.fail(f"Neo4j failed to access external CSV via LOAD CSV (Docker volume mount issue?): {e}")
            else:
                pytest.fail(f"Error during external LOAD CSV test: {e}")
        except Exception as e:
            pytest.fail(f"Unexpected error during external LOAD CSV test: {e}")
        finally:
            # Clean up the temporary CSV file
            if temp_csv_file_path.exists():
                os.remove(temp_csv_file_path)
                logger.info(f"Cleaned up temporary CSV file: {temp_csv_file_path}")

        logger.info("APOC LOAD CSV external resource access check passed.")
