import pytest
import os
import sys
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load environment variables once for all tests
load_dotenv()

@pytest.fixture(scope="session")
def neo4j_uri() -> str:
    """Provides the Neo4j URI from environment variables."""
    uri = os.getenv("NEO4J_URI")
    if not uri:
        pytest.fail("NEO4J_URI environment variable not set.")
    return uri

@pytest.fixture(scope="session")
def neo4j_admin_user() -> str:
    """Provides the Neo4j admin username from environment variables."""
    user = os.getenv("NEO4J_USER")
    if not user:
        pytest.fail("NEO4J_USER environment variable not set.")
    return user

@pytest.fixture(scope="session")
def neo4j_admin_password() -> str:
    """Provides the Neo4j admin password from environment variables."""
    password = os.getenv("NEO4J_PASSWORD")
    if not password:
        pytest.fail("NEO4J_PASSWORD environment variable not set.")
    return password

@pytest.fixture(scope="session")
def neo4j_elt_user() -> str:
    """Provides the Neo4j ETL username from environment variables."""
    user = os.getenv("NEO4J_ELT_USER")
    if not user:
        pytest.fail("NEO4J_ELT_USER environment variable not set.")
    return user

@pytest.fixture(scope="session")
def neo4j_elt_password() -> str:
    """Provides the Neo4j ETL password from environment variables."""
    password = os.getenv("NEO4J_ELT_PASSWORD")
    if not password:
        pytest.fail("NEO4J_ELT_PASSWORD environment variable not set.")
    return password

@pytest.fixture(scope="session")
def neo4j_admin_driver(neo4j_uri: str, neo4j_admin_user: str, neo4j_admin_password: str):
    """Provides a Neo4j driver connected as the admin user."""
    driver = None
    try:
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_admin_user, neo4j_admin_password))
        driver.verify_connectivity()
        yield driver
    finally:
        if driver:
            driver.close()

@pytest.fixture(scope="session")
def neo4j_elt_driver(neo4j_uri: str, neo4j_elt_user: str, neo4j_elt_password: str):
    """Provides a Neo4j driver connected as the ETL user."""
    driver = None
    try:
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_elt_user, neo4j_elt_password))
        driver.verify_connectivity()
        yield driver
    finally:
        if driver:
            driver.close()
