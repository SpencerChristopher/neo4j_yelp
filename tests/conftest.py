import os
import pytest
from unittest.mock import Mock, MagicMock
import pandas as pd
import subprocess
import time
import logging
import json
from pathlib import Path

from neo4j.exceptions import ServiceUnavailable

from src.loader import Neo4jLoader
from src.settings import settings
from src.logging_config import setup_logging
from tests.utils import csv_path, csv_chunks

# Setup logging first
setup_logging()

def _clear_logs():
    """Helper function to delete log files."""
    log_dir = Path("logs")
    if log_dir.exists() and log_dir.is_dir():
        for log_file in ["pipeline.log", "loader_critical.log", "validator_errors.log"]:
            file_path = log_dir / log_file
            if file_path.exists():
                try:
                    os.remove(file_path)
                    logging.getLogger(__name__).info(f"Cleared old log file: {file_path}")
                except OSError as e:
                    logging.getLogger(__name__).warning(f"Error clearing old log file {file_path}: {e}")

def pytest_configure(config):
    """Configures pytest settings, custom markers, and test data paths."""
    _clear_logs() # Clear logs at the very beginning of the test session
    project_root = Path(__file__).parent.parent
    # Point settings to the smaller test data files
    settings.DATA_DIR = project_root / "tests" / "data"
    settings.NEO4J_IMPORT_SUBDIR = "test_data"
    settings.BUSINESS_CSV = Path("test.business_small.csv")
    settings.BUSINESS_CITY_CSV = Path("test.business_city.csv")
    settings.REVIEW_CSV = Path("test.review_small.csv")
    settings.USER_CSV = Path("test.user_small.csv")
    settings.CATEGORY_CSV = Path("test.business_categories_small.csv")
    settings.FRIEND_CSV = Path("test.tiny_user_friendship.csv")

    # Register custom markers
    config.addinivalue_line("markers", "unit: Unit tests (fast, no external dependencies)")
    config.addinivalue_line("markers", "integration: Integration tests (requires external services)")     
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "database: Tests that require database access")
    config.addinivalue_line("markers", "neo4j: Tests that require Neo4j connection")

@pytest.fixture(scope="session")
def test_data_provider():
    """
    Provides dynamically loaded data statistics and sample IDs from the actual
    dataset specified in settings.DATA_DIR.
    """
    logger = logging.getLogger(__name__)
    data = {}

    try:
        # --- Users ---
        user_iter = csv_chunks(str(settings.USER_CSV))
        first_user_chunk = next(user_iter)
        data["sample_user_ids"] = first_user_chunk['user_id'].head(10).tolist()
        data["user_count"] = len(first_user_chunk) + sum(len(chunk) for chunk in user_iter)

        # --- Friendships ---
        friend_iter = csv_chunks(str(settings.FRIEND_CSV))
        first_friend_chunk = next(friend_iter)
        data["friendship_count"] = len(first_friend_chunk) + sum(len(chunk) for chunk in friend_iter)
        if not first_friend_chunk.empty:
            sample_friendship = first_friend_chunk.iloc[0]
            data["sample_friendship_user1"] = sample_friendship['user1']
            data["sample_friendship_user2"] = sample_friendship['user2']
        else:
            data["sample_friendship_user1"] = None
            data["sample_friendship_user2"] = None

        # --- Business ---
        business_iter = csv_chunks(str(settings.BUSINESS_CSV))
        first_business_chunk = next(business_iter)
        data["business_count"] = len(first_business_chunk) + sum(len(chunk) for chunk in business_iter)
        data["sample_business_ids"] = first_business_chunk['business_id'].head(10).tolist()
        data["sample_business_for_cat_id"] = first_business_chunk['business_id'].iloc[0]
        data["sample_business_for_cat_name"] = first_business_chunk['name'].iloc[0]


        # --- Reviews ---
        review_iter = csv_chunks(str(settings.REVIEW_CSV))
        first_review_chunk = next(review_iter)
        data["review_count"] = len(first_review_chunk) + sum(len(chunk) for chunk in review_iter)
        data["sample_review_ids"] = first_review_chunk['review_id'].head(10).tolist()
        # Get user and business IDs associated with the sample review
        if not first_review_chunk.empty:
            data["sample_review_id"] = first_review_chunk['review_id'].iloc[0]
            data["sample_review_user_id"] = first_review_chunk['user_id'].iloc[0]
            data["sample_review_business_id"] = first_review_chunk['business_id'].iloc[0]
        else:
            data["sample_review_id"] = None
            data["sample_review_user_id"] = None
            data["sample_review_business_id"] = None


        # --- City/State ---
        city_state_iter = csv_chunks(str(settings.BUSINESS_CITY_CSV))
        first_city_state_chunk = next(city_state_iter)
        state_codes = set(first_city_state_chunk['state'].tolist())
        city_state_pairs = set(
            zip(first_city_state_chunk['city'].tolist(), first_city_state_chunk['state'].tolist())
        )
        for chunk in city_state_iter:
            state_codes.update(chunk['state'].tolist())
            city_state_pairs.update(zip(chunk['city'].tolist(), chunk['state'].tolist()))
        data["state_count"] = len(state_codes)
        data["city_count"] = len(city_state_pairs)
        data["sample_state_code"] = first_city_state_chunk['state'].iloc[0]
        data["sample_city_name"] = first_city_state_chunk['city'].iloc[0]
        data["sample_city_state_code"] = first_city_state_chunk['state'].iloc[0]


        # --- Categories ---
        category_iter = csv_chunks(str(settings.CATEGORY_CSV))
        unique_categories = set()
        total_category_rels = 0
        for chunk in category_iter:
            exploded = chunk['category'].str.split(',').explode().str.strip().dropna()
            unique_categories.update(exploded.tolist())
            total_category_rels += len(exploded)
        data["category_node_count"] = len(unique_categories)
        data["category_relationship_count"] = total_category_rels # Corrected to count exploded categories
        if unique_categories:
            data["sample_category_name"] = next(iter(unique_categories))
        else:
            data["sample_category_name"] = None

        logger.info("Test data provider initialized with dynamic counts and samples.")

    except FileNotFoundError as e:
        pytest.fail(f"A test data file was not found: {e}. Ensure all test.*.csv files are in tests/data/")
    except Exception as e:
        pytest.fail(f"Failed to initialize test_data_provider: {e}")

    yield data
def _get_neo4j_container_id():
    """Returns the container ID of the Neo4j service if it's running, None otherwise."""
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "-q", "neo4j"],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    except (FileNotFoundError, Exception) as e:
        logging.getLogger(__name__).warning(f"Could not get Docker container ID: {e}")
        return None

@pytest.fixture(scope="session")
def neo4j_container():
    """
    Ensures a Neo4j Docker container is accessible for the test session.
    
    IMPORTANT: This fixture *assumes* the Neo4j container is already running
    (e.g., started manually with `docker compose up -d neo4j`). It will
    *not* start or stop the container.

    It will wait for the container to become ready and connected.
    """
    logger = logging.getLogger(__name__)

    # Wait for Neo4j to be ready
    max_retries = 60 # Increased retries as container startup can be slow
    for i in range(max_retries):
        try:
            loader = Neo4jLoader()
            loader.driver.verify_connectivity()
            loader.close()
            logger.warning("Neo4j container is ready and connected for testing.")
            break
        except ServiceUnavailable as e:
            logger.warning(f"Waiting for Neo4j... (attempt {i+1}/{max_retries}). Ensure container is running. Error: {e}")
            time.sleep(5)
    else:
        pytest.fail("Neo4j container did not become ready in time. Please ensure it is running (`docker compose up -d neo4j`) and accessible.")

    yield # Tests run here

    # No teardown - container lifecycle is managed externally
    logger.warning("Neo4j container lifecycle is managed externally. No teardown performed by fixture.")


@pytest.fixture(scope="session")
def neo4j_container_id(neo4j_container):
    """Provides the ID of the running neo4j container, ensuring it's up first."""
    return _get_neo4j_container_id()


@pytest.fixture(scope="module")
def neo4j_clear_db(neo4j_container):
    """
    Ensures the Neo4j database is clean before each test function.
    """
    loader = None
    try:
        loader = Neo4jLoader()
        logger = logging.getLogger(__name__)

        logger.info("Fixture neo4j_clear_db: Clearing Neo4j database...")
        with loader.driver.session() as session:
            result = session.run("""
                CALL apoc.periodic.iterate("MATCH (n) RETURN n", "DETACH DELETE n", {batchSize: 1000})
                YIELD batches, total RETURN batches, total
            """).single()
            logger.info(f"Fixture neo4j_clear_db: APOC deletion complete. Batches: {result['batches']}, Total deleted: {result['total']}.")
        
        logger.info("Fixture neo4j_clear_db: Re-applying Neo4j constraints and indexes...")
        with loader.driver.session() as session:
            for query in settings.NEO4J_CONSTRAINTS_AND_INDEXES:
                try:
                    session.run(query).consume()
                except Exception as e:
                    logger.warning(f"Could not apply constraint/index (might exist): {e}")
        logger.info("Fixture neo4j_clear_db: Neo4j constraints and indexes re-applied.")

    finally:
        if loader:
            loader.close()

@pytest.fixture(scope="module")
def neo4j_loader(neo4j_clear_db):
    """Provides a fresh Neo4jLoader instance connected to a clean database for a test function."""
    loader = Neo4jLoader()
    yield loader
    loader.close()

@pytest.fixture
def mock_neo4j_driver():
    """Mock Neo4j driver for unit tests."""
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_transaction = Mock()
    mock_result = Mock()
    mock_driver.session.return_value = mock_session
    mock_session.begin_transaction.return_value.__enter__.return_value = mock_transaction
    mock_transaction.run.return_value = mock_result
    mock_result.data.return_value = []
    mock_result.single.return_value = None
    return mock_driver

@pytest.fixture(scope="class")
def sample_business_data():
    return {
        "business_id": "abc123", "name": "Test Restaurant", "city": "Test City", "state": "TS",
        "postal_code": "12345", "latitude": 40.7128, "longitude": -74.0060,
        "stars": 4.5, "review_count": 100, "is_open": 1,
    }

@pytest.fixture(scope="class")
def sample_user_data():
    return {
        "user_id": "user123", "name": "John Doe", "review_count": 50,
        "yelping_since": "2018-01-01 00:00:00", "useful": 100, "funny": 50, "cool": 75, "fans": 10,
        "average_stars": 4.2, "compliment_hot": 0, "compliment_more": 0, "compliment_profile": 0,
        "compliment_cute": 0, "compliment_list": 0, "compliment_note": 0, "compliment_plain": 0,
        "compliment_cool": 0, "compliment_funny": 0, "compliment_writer": 0, "compliment_photos": 0,
    }

@pytest.fixture(scope="class")
def sample_review_data():
    return {
        "review_id": "rev123", "user_id": "user123", "business_id": "abc123",
        "stars": 5, "useful": 10, "funny": 2, "cool": 5, "date": "15/01/2023 12:30",
        "sentiment_score": 0.8, "confidence": 0.9,
    }
