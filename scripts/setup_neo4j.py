import os
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ClientError, ServiceUnavailable

def setup_neo4j_database():
    """
    Sets up the Neo4j database with schema constraints/indexes using a single user (for Community Edition).
    """
    load_dotenv()

    # Neo4j Credentials for Setup
    neo4j_uri = os.getenv("NEO4J_URI")
    neo4j_user = os.getenv("NEO4J_USER")
    neo4j_password = os.getenv("NEO4J_PASSWORD")

    if not all([neo4j_uri, neo4j_user, neo4j_password]):
        print("Error: All Neo4j environment variables (URI, USER, PASSWORD) must be set in the .env file.")
        return

    driver = None
    try:
        # 1. Connect to Neo4j
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        driver.verify_connectivity()
        print("Successfully connected to Neo4j.")

        with driver.session() as session:
            # 2. Create Constraints and Indexes
            print("Creating unique constraints and indexes...")
            constraints_and_indexes = [

                # --- Business ---
                "CREATE CONSTRAINT business_id_unique IF NOT EXISTS "
                "FOR (b:Business) REQUIRE b.business_id IS UNIQUE",

                "CREATE INDEX business_name_idx IF NOT EXISTS "
                "FOR (b:Business) ON (b.name)",

                # --- User ---
                "CREATE CONSTRAINT user_id_unique IF NOT EXISTS "
                "FOR (u:User) REQUIRE u.user_id IS UNIQUE",

                "CREATE INDEX user_name_idx IF NOT EXISTS "
                "FOR (u:User) ON (u.name)",

                # --- Review ---
                "CREATE CONSTRAINT review_id_unique IF NOT EXISTS "
                "FOR (r:Review) REQUIRE r.review_id IS UNIQUE",

                "CREATE INDEX review_date_idx IF NOT EXISTS "
                "FOR (r:Review) ON (r.date)",

                # --- State ---
                "CREATE CONSTRAINT state_code_unique IF NOT EXISTS "
                "FOR (s:State) REQUIRE s.code IS UNIQUE",

                # --- City ---
                "CREATE CONSTRAINT city_name_state_unique IF NOT EXISTS "
                "FOR (c:City) REQUIRE (c.name, c.state_code) IS UNIQUE",

                # --- Postal Code ---
                "CREATE CONSTRAINT postal_code_unique IF NOT EXISTS "
                "FOR (p:PostalCode) REQUIRE p.code IS UNIQUE",

                # --- Category ---
                "CREATE CONSTRAINT category_name_unique IF NOT EXISTS "
                "FOR (c:Category) REQUIRE c.name IS UNIQUE"
            ]

            for query in constraints_and_indexes:
                try:
                    session.run(query)
                    print(f"Executed: {query}")
                except ClientError as e:
                    if "already exists" in str(e):
                        print(f"Constraint/Index already exists: {query}")
                    else:
                        print(f"Error executing '{query}': {e}")
                        raise e
            print("All constraints and indexes processed.")

    except AuthError:
        print(f"Error: Authentication failed for user '{neo4j_user}'. Check credentials.")
        return
    except ServiceUnavailable:
        print(f"Error: Could not connect to Neo4j at {neo4j_uri}. Please ensure the database is running.")
        return
    except Exception as e:
        print(f"Error during setup: {e}")
        return
    finally:
        if driver:
            driver.close()

if __name__ == "__main__":
    setup_neo4j_database()
