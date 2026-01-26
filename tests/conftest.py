"""
Pytest configuration file for shared fixtures and plugins.
"""
import os
import pytest
from dotenv import load_dotenv
from unittest.mock import Mock, MagicMock

# New imports for Neo4j fixtures
import subprocess
import time
import logging

from neo4j.exceptions import ServiceUnavailable

from src.loader import Neo4jLoader
from src.settings import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD # Use NEO4J_USER for admin

from src.logging_config import setup_logging

# Load environment variables for testing
load_dotenv()
setup_logging()


# Register custom markers
def pytest_configure(config):
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


@pytest.fixture(scope="session")
def neo4j_container():
    """Ensures Neo4j Docker container is running for the test session."""
    logger = logging.getLogger(__name__)
    logger.info("Starting Neo4j Docker container...")

    try:
        # Start Neo4j container
        subprocess.run(["docker-compose", "up", "-d", "neo4j"], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Wait for Neo4j to be ready
        max_retries = 30
        for i in range(max_retries):
            try:
                driver = Neo4jLoader(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD).driver
                driver.verify_connectivity()
                driver.close()
                logger.info("Neo4j container is ready.")
                break
            except ServiceUnavailable:
                logger.info(f"Waiting for Neo4j... (attempt {i+1}/{max_retries})")
                time.sleep(2)
        else:
            raise Exception("Neo4j container did not become ready in time.")

        yield # Run tests

    finally:
        logger.info("Stopping Neo4j Docker container...")
        subprocess.run(["docker-compose", "down", "-v", "--remove-orphans"], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info("Neo4j Docker container stopped and volumes removed.")


@pytest.fixture(scope="function") # Use function scope for clean state per test
def neo4j_clear_db(neo4j_container):
    """
    Provides a clean Neo4j database for each test function by clearing all data
    and re-applying constraints/indexes.
    """
    loader = None
    try:
        loader = Neo4jLoader(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
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