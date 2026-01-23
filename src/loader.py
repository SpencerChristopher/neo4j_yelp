from neo4j import GraphDatabase, Driver
from typing import List, Dict, Any
from src.settings import (
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    NEO4J_ELT_USER,
    NEO4J_ELT_PASSWORD,
)
from src.models import City, State, PostalCode
import logging

logger = logging.getLogger(__name__)


class Neo4jLoader:
    def __init__(self, uri: str, username: str, password: str):
        try:
            self.driver: Driver = GraphDatabase.driver(uri, auth=(username, password))
            self.driver.verify_connectivity()
            logger.info("Neo4j driver initialized and connected.")
        except Exception as e:
            logger.error("Failed to connect to Neo4j", exc_info=True)
            raise

    def close(self):
        if self.driver:
            self.driver.close()
            logger.info("Neo4j driver closed.")

    def _execute_query_batch(self, query: str, data: List[Dict[str, Any]], label: str) -> int:
        if not data:
            return 0

        try:
            with self.driver.session() as session:
                summary = session.execute_write(
                    lambda tx: tx.run(query, data=data).consume()
                )

                counters = summary.counters
                created = (
                    counters.nodes_created
                    + counters.relationships_created
                )

                logger.debug(
                    "%s batch executed | nodes_created=%d | rels_created=%d",
                    label,
                    counters.nodes_created,
                    counters.relationships_created,
                )

                return created

        except Exception:
            logger.error("Error loading batch: %s", label, exc_info=True)
            return 0

    # ----------------------------
    # Node loaders
    # ----------------------------

    def load_states(self, states: List[State]) -> int:
        if not states:
            return 0

        query = """
        UNWIND $data AS state
        MERGE (:State {code: state.code})
        """

        data = [s.model_dump() for s in states]
        return self._execute_query_batch(query, data, "State")

    def load_cities(self, cities: List[City]) -> int:
        if not cities:
            return 0

        query = """
        UNWIND $data AS city
        MERGE (:City {name: city.name, state_code: city.state_code})
        """

        data = [c.model_dump() for c in cities]
        return self._execute_query_batch(query, data, "City")

    def load_postal_codes(self, postal_codes: List[PostalCode]) -> int:
        if not postal_codes:
            return 0

        query = """
        UNWIND $data AS pc
        MERGE (:PostalCode {code: pc.code})
        """

        data = [p.model_dump() for p in postal_codes]
        return self._execute_query_batch(query, data, "PostalCode")

    def load_businesses(self, businesses: List[Dict[str, Any]]) -> int:
        if not businesses:
            return 0

        query = """
        UNWIND $data AS b
        MERGE (biz:Business {business_id: b.business_id})
        SET biz.name = b.name,
            biz.stars = b.stars,
            biz.is_open = b.is_open
        """

        return self._execute_query_batch(query, businesses, "Business")

    # ----------------------------
    # Relationship loaders
    # ----------------------------

    def create_relationships(self, relationships: List[Dict[str, Any]]) -> int:
        if not relationships:
            return 0

        total_created = 0
        grouped: Dict[str, List[Dict[str, Any]]] = {}

        for rel in relationships:
            grouped.setdefault(rel["relationship_type"], []).append(rel)

        for rel_type, rels in grouped.items():

            if rel_type == "CLAIMS_STATE":
                query = """
                UNWIND $data AS r
                MATCH (c:City {name: r.from_node_id_value, state_code: r.from_node_id_aux_value})
                MATCH (s:State {code: r.to_node_id_value})
                MERGE (c)-[:CLAIMS_STATE]->(s)
                """
                total_created += self._execute_query_batch(query, rels, rel_type)

            elif rel_type == "LOCATED_NEAR":
                query = """
                UNWIND $data AS r
                MATCH (b:Business {business_id: r.from_node_id_value})
                MATCH (c:City {name: r.to_node_id_value, state_code: r.to_node_id_aux_value})
                MERGE (b)-[rel:LOCATED_NEAR]->(c)
                SET rel.latitude = r.properties['latitude'],
                    rel.longitude = r.properties['longitude']
                """
                total_created += self._execute_query_batch(query, rels, rel_type)

            elif rel_type == "CLAIMS_POSTAL_CODE":
                query = """
                UNWIND $data AS r
                MATCH (b:Business {business_id: r.from_node_id_value})
                MATCH (p:PostalCode {code: r.to_node_id_value})
                MERGE (b)-[:CLAIMS_POSTAL_CODE]->(p)
                """
                total_created += self._execute_query_batch(query, rels, rel_type)

            else:
                logger.warning("Unknown relationship type: %s", rel_type)

        return total_created


    def load_users(self, users: list[dict]) -> int:
        if not users:
            return 0

        query = """
        UNWIND $data AS u
        MERGE (user:User {user_id: u.user_id})
        SET user.name = u.name,
            user.review_count = u.review_count,
            user.yelping_since = u.yelping_since,
            user.fans = u.fans,
            user.average_stars = u.average_stars,
            user.compliments = u.compliments
        RETURN count(user)
        """
        return self._execute_query_batch(query, users, "Users")
