import os
import sys
import os

# Add the project root to the sys.path
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, '..'))
sys.path.insert(0, project_root)

from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable
from src.settings import settings


def clear_database():
    """
    Deletes ALL nodes and relationships in the database.
    ADMIN ONLY — a very destructive operation.
    """

    uri = settings.NEO4J_URI
    user = settings.NEO4J_USER
    password = settings.NEO4J_PASSWORD

    if not all([uri, user, password]):
        raise RuntimeError("Missing Neo4j admin credentials in environment")

    driver = None
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password),
            connection_acquisition_timeout=600,  # 10 minutes
            max_transaction_retry_time=300       # 5 minutes
        )
        driver.verify_connectivity()
        print("****\n Connected as admin\n****")

        with driver.session() as session:
            # Check if the database is empty
            result = session.run("MATCH (n) RETURN count(n) as count").single()
            if result['count'] == 0:
                print("Database is already empty. No action taken.")
                return
            
            print("Deleting all nodes and relationships...")
            # Use apoc.periodic.iterate for batching to handle large databases safely.
            # Stream IDs to reduce memory pressure, and delete in larger batches.
            session.run("""
                CALL apoc.periodic.iterate(
                    "MATCH (n) RETURN id(n) AS id",
                    "MATCH (n) WHERE id(n) = id DETACH DELETE n",
                    {batchSize: 10000, parallel: false, iterateList: true, retries: 5}
                ) YIELD batches, total
                RETURN batches, total
            """)
            
            # Verify deletion
            result = session.run("MATCH (n) RETURN count(n) as count").single()
            if result['count'] == 0:
                print("\nDatabase cleared successfully.")
            else:
                print(f"\n!!! Warning: {result['count']} nodes still remain after clearing.")


    except AuthError:
        print("!!! Authentication failed (admin user required)")
    except ServiceUnavailable:
        print("!!! \nNeo4j service unavailable\n !!!")
    finally:
        if driver:
            driver.close()


if __name__ == "__main__":
    clear_database()
