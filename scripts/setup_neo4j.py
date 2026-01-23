import os
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ClientError, ServiceUnavailable

def setup_neo4j_database():
    """
    Sets up the Neo4j database with schema constraints/indexes using admin credentials.
    NOTE: User/role creation and granular privilege granting is not supported in
    Neo4j Community Edition via remote Cypher scripts. If a dedicated 'elt_user'
    is desired, it must be created and granted privileges manually (e.g., in Neo4j Browser).
    """
    load_dotenv()

    # Admin Credentials for Setup
    admin_uri = os.getenv("NEO4J_URI")
    admin_user = os.getenv("NEO4J_USER")
    admin_password = os.getenv("NEO4J_PASSWORD")

    # ETL User Credentials (for verification - will fail if user not manually created)
    elt_user = os.getenv("NEO4J_ELT_USER")
    elt_password = os.getenv("NEO4J_ELT_PASSWORD")

    if not all([admin_uri, admin_user, admin_password]):
        print("Error: All Neo4j Admin environment variables (URI, USER, PASSWORD) must be set in the .env file.")
        return

    admin_driver = None
    try:
        # 1. Connect as Admin
        admin_driver = GraphDatabase.driver(admin_uri, auth=(admin_user, admin_password))
        admin_driver.verify_connectivity()
        print("Admin: Successfully connected to Neo4j.")

        with admin_driver.session() as session:
            # 2. Create Constraints and Indexes
            print("Admin: Creating unique constraints and indexes...")
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
                    print(f"Admin: Executed: {query}")
                except ClientError as e:
                    if "already exists" in str(e):
                        print(f"Admin: Constraint/Index already exists: {query}")
                    else:
                        print(f"Admin: Error executing '{query}': {e}")
                        raise e
            print("Admin: All constraints and indexes processed.")

    except AuthError:
        print(f"Error: Admin authentication failed for user '{admin_user}'. Check credentials.")
        return
    except ServiceUnavailable:
        print(f"Error: Could not connect to Neo4j at {admin_uri}. Please ensure the database is running.")
        return
    except Exception as e:
        print(f"Error during setup: {e}")
        return
    finally:
        if admin_driver:
            admin_driver.close()

    # 3. Verify ETL User Connectivity (requires manual setup of elt_user and privileges if desired)
    print(f"\nAttempting to verify ETL user '{elt_user}' connectivity (requires manual setup of user/privileges)...")
    if not all([elt_user, elt_password]):
        print("Warning: NEO4J_ELT_USER and NEO4J_ELT_PASSWORD are not fully set in .env. Skipping ETL user verification.")
        return
        
    elt_driver = None
    try:
        elt_driver = GraphDatabase.driver(admin_uri, auth=(elt_user, elt_password))
        elt_driver.verify_connectivity()
        print(f"ETL User: Successfully connected to Neo4j as '{elt_user}'.")
        # Optional: Run a simple query to ensure basic read access
        with elt_driver.session() as session:
            session.run("MATCH (n) RETURN n LIMIT 1")
            print(f"ETL User: Basic read access verified.")

    except AuthError:
        print(f"Error: ETL user '{elt_user}' authentication failed. This user or its privileges might need manual setup.")
    except ServiceUnavailable:
        print(f"Error: Could not connect to Neo4j with ETL user at {admin_uri}.")
    except Exception as e:
        print(f"Error during ETL user verification: {e}")
    finally:
        if elt_driver:
            elt_driver.close()

if __name__ == "__main__":
    setup_neo4j_database()
