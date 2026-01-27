import os
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable
from src.settings import settings


def reset_schema():
    """
    Drops ALL constraints and indexes in the database.
    ADMIN ONLY — destructive operation.
    """

    uri = settings.NEO4J_URI
    user = settings.NEO4J_USER
    password = settings.NEO4J_PASSWORD

    if not all([uri, user, password]):
        raise RuntimeError("Missing Neo4j admin credentials in environment")

    driver = None
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        print("****\n Connected as admin\n****")

        with driver.session() as session:
            # --- DROP CONSTRAINTS ---
            constraints = session.run("SHOW CONSTRAINTS").data()
            for c in constraints:
                name = c["name"]
                session.run(f"DROP CONSTRAINT {name}")
                print(f"\t Dropped constraint: {name}")

            # --- DROP INDEXES ---
            indexes = session.run("SHOW INDEXES").data()
            for idx in indexes:
                name = idx["name"]
                session.run(f"DROP INDEX {name}")
                print(f"\tDropped index: {name}")

        print("\n🎉 Schema reset complete")

    except AuthError:
        print("!!! Authentication failed (admin user required)")
    except ServiceUnavailable:
        print("!!! \nNeo4j service unavailable\n !!!")
    finally:
        if driver:
            driver.close()


if __name__ == "__main__":
    reset_schema()