import os
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

def clear_database():
    """
    Deletes ALL nodes and relationships in the database.
    ADMIN ONLY — a very destructive operation.
    """

    load_dotenv()

    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")

    if not all([uri, user, password]):
        raise RuntimeError("Missing Neo4j admin credentials in environment")

    driver = None
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        print("****\n Connected as admin\n****")

        with driver.session() as session:
            # Check if the database is empty
            result = session.run("MATCH (n) RETURN count(n) as count").single()
            if result['count'] == 0:
                print("Database is already empty. No action taken.")
                return
            
            print("Deleting all nodes and relationships...")
            # Use apoc.periodic.iterate for batching, which is safer for large databases
            # However, for a test setup, a simple DETACH DELETE is usually fine.
            # Using DETACH DELETE for simplicity here.
            session.run("MATCH (n) DETACH DELETE n")
            
            # Verify deletion
            result = session.run("MATCH (n) RETURN count(n) as count").single()
            if result['count'] == 0:
                print("\n🎉 Database cleared successfully.")
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
