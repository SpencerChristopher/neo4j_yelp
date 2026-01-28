import os
import pytest
from unittest.mock import Mock, MagicMock

import sys
# Add the project root to sys.path to ensure modules can be found
sys.path.insert(0, os.path.abspath('.'))

# New imports for Neo4j fixtures
import subprocess
import time
import logging

from neo4j.exceptions import ServiceUnavailable

from src.loader import Neo4jLoader
from src.settings import settings

from src.logging_config import setup_logging

# Setup logging first
setup_logging()


# Register custom markers
def pytest_configure(config):
    # Directly set test-specific settings. This happens once at the start of the test session.
    # No monkeypatch needed as these are global module attributes.
    from pathlib import Path # Import Path here
    settings.NEO4J_URI = "bolt://localhost:7687"
    settings.DATA_DIR = Path(os.path.join(os.path.dirname(__file__), "data")) # Converted to Path object

    config.addinivalue_line(
        "markers", "unit: Unit tests (fast, no external dependencies)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (requires external services)"
    )
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "database: Tests that require database access")
    config.addinivalue_line(
        "markers", "neo4j: Tests that require Neo4j connection"
    )

@pytest.fixture(scope="session")
def test_data_dir():
    """Return the path to test data directory."""
    return os.path.join(os.path.dirname(__file__), "data")

def _is_neo4j_running():
    """Checks if the neo4j Docker container is running and healthy."""
    try:
        # Check if the container exists and is running
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}}", "neo4j-neo4j-1"], # Assuming service name 'neo4j' from docker-compose.yml forms container name neo4j-neo4j-1
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0 and result.stdout.strip() == "running":
            # You might want to add a more thorough health check here,
            # e.g., using `docker inspect -f "{{.State.Health.Status}}"`
            return True
        return False
    except FileNotFoundError:
        logging.getLogger(__name__).warning("Docker command not found. Please ensure Docker is installed and in PATH.")
        return False
    except Exception as e:
        logging.getLogger(__name__).error(f"Error checking Docker container status: {e}")
        return False


@pytest.fixture(scope="session")
def neo4j_container():
    """Ensures Neo4j Docker container is running for the test session."""
    logger = logging.getLogger(__name__)

    if _is_neo4j_running():
        logger.info("Neo4j Docker container already running. Reusing existing instance.")
    else:
        logger.info("Starting Neo4j Docker container...")
        try:
            subprocess.run(["docker-compose", "up", "-d", "neo4j"], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            logger.error(f"Failed to start Neo4j Docker container: {e}", exc_info=True)
            raise

    # Wait for Neo4j to be ready
    max_retries = 30
    for i in range(max_retries):
        try:
            loader = Neo4jLoader()
            loader.driver.verify_connectivity()
            loader.close()
            logger.info("Neo4j container is ready.")
            break
        except ServiceUnavailable as e:
            logger.info(f"Waiting for Neo4j... (attempt {i+1}/{max_retries})")
            logger.debug(f"Neo4j connection error: {e}")
            time.sleep(5)
    else:
        raise Exception("Neo4j container did not become ready in time.")

    yield # Run tests

    # The container is not stopped here, it persists for manual management.
    # User is responsible for docker-compose down when done.


@pytest.fixture(scope="function") # Use function scope for clean state per test
def neo4j_clear_db(neo4j_container):
    """
    Provides a clean Neo4j database for each test function by clearing all data
    and re-applying constraints/indexes.
    """
    loader = None
    try:
        loader = Neo4jLoader()
        logger = logging.getLogger(__name__)

        # 1. Clear existing data
        logger.info("Clearing Neo4j database...")
        with loader.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n").consume()
        logger.info("Neo4j database cleared.")

        # 2. Re-apply constraints and indexes
        logger.info("Re-applying Neo4j constraints and indexes...")
        # Assuming setup_neo4j.py script sets up constraints
        # It's better to call the function directly if possible
        # For now, we'll shell out or re-implement the core logic.
        # Let's re-implement a minimal version for constraints.
        constraints_and_indexes = [
            "CREATE CONSTRAINT business_id_unique IF NOT EXISTS FOR (b:Business) REQUIRE b.business_id IS UNIQUE",
            "CREATE INDEX business_name_idx IF NOT EXISTS FOR (b:Business) ON (b.name)",
            "CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
            "CREATE INDEX user_name_idx IF NOT EXISTS FOR (u:User) ON (u.name)",
            "CREATE CONSTRAINT review_id_unique IF NOT EXISTS FOR (r:Review) REQUIRE r.review_id IS UNIQUE",
            "CREATE INDEX review_date_idx IF NOT EXISTS FOR (r:Review) ON (r.date)",
            "CREATE CONSTRAINT state_code_unique IF NOT EXISTS FOR (s:State) REQUIRE s.code IS UNIQUE",
            "CREATE CONSTRAINT city_name_state_unique IF NOT EXISTS FOR (c:City) REQUIRE (c.name, c.state_code) IS UNIQUE",
            "CREATE CONSTRAINT postal_code_unique IF NOT EXISTS FOR (p:PostalCode) REQUIRE p.code IS UNIQUE",
            "CREATE CONSTRAINT category_name_unique IF NOT EXISTS FOR (c:Category) REQUIRE c.name IS UNIQUE"
        ]
        with loader.driver.session() as session:
            for query in constraints_and_indexes:
                try:
                    session.run(query).consume()
                except Exception as e:
                    logger.warning(f"Failed to apply constraint/index '{query}': {e}")
        logger.info("Neo4j constraints and indexes re-applied.")

        yield loader # Yield the loader for the test to use

    finally:
        if loader:
            loader.close()


@pytest.fixture(scope="function") # This provides the loader for tests to use
def neo4j_loader(neo4j_clear_db):
    """Provides a Neo4jLoader instance connected to a clean database."""
    return neo4j_clear_db


@pytest.fixture
def mock_neo4j_driver():
    """Mock Neo4j driver for unit tests."""
    mock_driver = MagicMock() # Use MagicMock for context manager behavior
    mock_session = MagicMock()
    mock_transaction = Mock()
    mock_result = Mock()

    # Configure the session to act as a context manager
    mock_driver.session.return_value = mock_session
    mock_session.begin_transaction.return_value.__enter__.return_value = mock_transaction
    mock_transaction.run.return_value = mock_result
    mock_result.data.return_value = []
    mock_result.single.return_value = None

    return mock_driver


@pytest.fixture(scope="class")
def sample_business_data():
    """Sample business data for testing, aligned with src/models/business.py."""
    return {
        "business_id": "abc123",
        "name": "Test Restaurant",
        "city": "Test City",
        "state": "TS",
        "postal_code": "12345",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "stars": 4.5,
        "review_count": 100,
        "is_open": 1,
    }


@pytest.fixture(scope="class")
def sample_user_data():
    """Sample user data for testing, aligned with src/models/user.py."""
    return {
        "user_id": "user123",
        "name": "John Doe",
        "review_count": 50,
        "yelping_since": "01/01/2018 00:00",
        "useful": 100,
        "funny": 50,
        "cool": 75,
        "fans": 10,
        "average_stars": 4.2,
        "compliment_hot": 0,
        "compliment_more": 0,
        "compliment_profile": 0,
        "compliment_cute": 0,
        "compliment_list": 0,
        "compliment_note": 0,
        "compliment_plain": 0,
        "compliment_cool": 0,
        "compliment_funny": 0,
        "compliment_writer": 0,
        "compliment_photos": 0,
    }


@pytest.fixture(scope="class")
def sample_review_data():
    """Sample review data for testing, aligned with src/models/review.py."""
    return {
        "review_id": "rev123",
        "user_id": "user123",
        "business_id": "abc123",
        "stars": 5,
        "useful": 10,
        "funny": 2,
        "cool": 5,
        "date": "15/01/2023 12:30",
        "sentiment_score": 0.8,
        "confidence": 0.9,
    }
