import os
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

def health_check():
    """
    Checks the connection to the Neo4j database, retrieves version, and lists key plugins.
    """
    load_dotenv()

    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")

    if not all([uri, user, password]):
        print("Error: NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD must be set in the .env file.")
        return

    driver = None
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        print("Successfully connected to Neo4j.")
        print(f"   - URI: {uri}")
        print(f"   - User: {user}")

        with driver.session() as session:
            # Get Neo4j Version and Edition
            result = session.run("CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition").single()
            if result:
                print("\nNeo4j Instance Details:")
                print(f"   - {result['name']} Version: {result['versions'][0]}") # versions is a list, take the first
                print(f"   - Edition: {result['edition']}")

            # Get Installed Plugins (APOC & GDS)
            plugin_result = session.run("""
                SHOW PROCEDURES YIELD name 
                WHERE name STARTS WITH 'apoc.' OR name STARTS WITH 'gds.' 
                RETURN collect(DISTINCT split(name, '.')[0]) AS plugins
            """).single()
            if plugin_result and plugin_result['plugins']:
                print("\nInstalled Plugins:")
                for plugin in sorted(plugin_result['plugins']):
                    print(f"   - {plugin}")
            else:
                print("\nWarning: Could not detect APOC or GDS plugins.")

    except AuthError:
        print(f"Error: Authentication failed. Please check the credentials for user '{user}'.")
    except ServiceUnavailable:
        print(f"Error: Could not connect to Neo4j at {uri}. Please ensure the database is running.")
    except Exception as e:
        print(f"Error: An unexpected error occurred: {e}")
    finally:
        if driver is not None:
            driver.close()

if __name__ == "__main__":
    health_check()
