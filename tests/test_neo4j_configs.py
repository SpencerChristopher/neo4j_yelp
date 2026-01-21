import pytest
import logging
from neo4j.exceptions import AuthError, ServiceUnavailable

# Configure basic logging for the test script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_neo4j_admin_connectivity(neo4j_admin_driver):
    """Verifies that the admin user can connect to the Neo4j database."""
    logger.info("Testing admin user connectivity to Neo4j...")
    try:
        neo4j_admin_driver.verify_connectivity()
        logger.info("Admin: Successfully connected to Neo4j.")
    except (AuthError, ServiceUnavailable) as e:
        pytest.fail(f"Admin: Failed to connect to Neo4j: {e}")
    except Exception as e:
        pytest.fail(f"Admin: An unexpected error occurred during connectivity test: {e}")

def test_neo4j_version_and_edition(neo4j_admin_driver):
    """Verifies the Neo4j version and edition using the admin driver."""
    logger.info("Verifying Neo4j version and edition...")
    try:
        with neo4j_admin_driver.session() as session:
            result = session.run("CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition").single()
            assert result is not None, "Neo4j components information not found."
            logger.info(f"Neo4j Instance Details: {result['name']} Version: {result['versions'][0]}, Edition: {result['edition']}")
            
            # Assert expected values (can be made more dynamic if needed)
            assert result['name'] == "Neo4j Kernel"
            assert result['versions'][0].startswith("5."), "Expected Neo4j 5.x version."
            assert result['edition'] == "community"
    except Exception as e:
        pytest.fail(f"Failed to retrieve Neo4j version and edition: {e}")

def test_neo4j_plugins_installed(neo4j_admin_driver):
    """Verifies that APOC and GDS plugins are installed."""
    logger.info("Verifying Neo4j plugin installation (APOC and GDS)...")
    try:
        with neo4j_admin_driver.session() as session:
            plugin_result = session.run("""
                SHOW PROCEDURES YIELD name 
                WHERE name STARTS WITH 'apoc.' OR name STARTS WITH 'gds.' 
                RETURN collect(DISTINCT split(name, '.')[0]) AS plugins
            """).single()
            
            assert plugin_result is not None, "Could not retrieve plugin information."
            installed_plugins = set(plugin_result['plugins'])
            
            logger.info(f"Detected plugins: {installed_plugins}")
            assert "apoc" in installed_plugins, "APOC plugin not found."
            assert "gds" in installed_plugins, "GDS plugin not found."
            logger.info("APOC and GDS plugins confirmed installed.")
    except Exception as e:
        pytest.fail(f"Failed to verify Neo4j plugins: {e}")

def test_elt_user_connectivity(neo4j_elt_driver, neo4j_elt_user):
    """Verifies that the ETL user can connect and has basic read access."""
    logger.info(f"Testing ETL user '{neo4j_elt_user}' connectivity and basic read access...")
    try:
        neo4j_elt_driver.verify_connectivity()
        logger.info(f"ETL User: Successfully connected to Neo4j as '{neo4j_elt_user}'.")
        with neo4j_elt_driver.session() as session:
            # Attempt a simple read query
            session.run("MATCH (n) RETURN n LIMIT 1")
            logger.info(f"ETL User: Basic read access verified for '{neo4j_elt_user}'.")
    except AuthError:
        pytest.fail(f"ETL User: Authentication failed for '{neo4j_elt_user}'. Check credentials/roles.")
    except ServiceUnavailable as e:
        pytest.fail(f"ETL User: Could not connect to Neo4j with '{neo4j_elt_user}': {e}.")
    except Exception as e:
        pytest.fail(f"ETL User: An unexpected error occurred during connectivity test for '{neo4j_elt_user}': {e}")
