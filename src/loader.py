from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable, TransientError, DatabaseError, ClientError
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from typing import List, Dict, Any, Tuple
import time
import os
import json
from datetime import datetime
import logging
import gc

from src.settings import settings

logger = logging.getLogger(__name__)


class Neo4jLoader:
    def __init__(self):
        try:
            self.driver: Driver = GraphDatabase.driver(
                settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
            self._verify_connection()
            logger.info("Neo4j driver initialized and connected.")

            # Batch sizing from settings for consistency and configurability
            self.current_batch_size = settings.BATCH_SIZE
            self.consecutive_failures = 0
            self.max_batch_size = settings.BATCH_SIZE * 5  # Allow for dynamic increase
            self.min_batch_size = max(50, settings.BATCH_SIZE // 10)  # Ensure minimum is reasonable
            self.total_failed_records = 0
            self.last_memory_check = time.time()
            self.memory_pressure = False

        except Exception as e:
            logger.error("Failed to connect to Neo4j after retries", exc_info=True)
            raise

    def __enter__(self):
        logger.info("Entering Neo4jLoader context.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        if exc_type:
            logger.error(f"Exited Neo4jLoader context with an exception: {exc_val}", exc_info=True)
        else:
            logger.info("Exited Neo4jLoader context gracefully.")

    def close(self):
        if self.driver:
            self.driver.close()
            logger.info("Neo4j driver closed.")

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(ServiceUnavailable),
        reraise=True
    )
    def _verify_connection(self):
        logger.info("Attempting to verify Neo4j connectivity...")
        self.driver.verify_connectivity()
        logger.info("Neo4j connectivity verified.")

    def _check_memory_pressure(self):
        """Check if we should back off due to memory pressure."""
        current_time = time.time()
        if current_time - self.last_memory_check < 5:  # Check every 5 seconds
            return self.memory_pressure

        self.last_memory_check = current_time
        try:
            # Simple memory check - reduce batch size if Python memory is high
            import psutil
            process = psutil.Process()
            memory_percent = process.memory_percent()

            if memory_percent > 70:  # 70% memory usage
                logger.warning(f"Memory pressure detected: {memory_percent:.1f}%")
                self.memory_pressure = True
                return True
            else:
                self.memory_pressure = False
                return False
        except ImportError:
            # psutil not available, skip memory check
            return False

    def _adjust_batch_size(self, success: bool):
        """Adaptively adjust batch size based on success/failure and memory pressure."""
        if self._check_memory_pressure():
            # Aggressively reduce batch size on memory pressure
            self.current_batch_size = max(self.min_batch_size, self.current_batch_size // 2)
            logger.warning(f"Memory pressure - reduced batch size to {self.current_batch_size}")
            self.consecutive_failures = 0
            return

        if success:
            self.consecutive_failures = 0
            # Very conservative increase
            if self.current_batch_size < self.max_batch_size:
                self.current_batch_size = min(
                    int(self.current_batch_size * 1.2),  # Gradual increase (20%)
                    self.max_batch_size
                )
                logger.debug(f"Gradually increased batch size to {self.current_batch_size}")
        else:
            self.consecutive_failures += 1
            # Aggressive reduction on failure
            new_size = max(
                self.current_batch_size // 2,
                self.min_batch_size
            )
            if new_size < self.current_batch_size:
                self.current_batch_size = new_size
                logger.warning(
                    f"Decreased batch size to {self.current_batch_size} after {self.consecutive_failures} failures")

            # If many failures, pause longer
            if self.consecutive_failures >= 2:
                logger.warning(f"Multiple consecutive failures, pausing for 5 seconds")
                time.sleep(5)

    def _write_batch_dead_letters(self, failed_records: List[Dict[str, Any]]) -> None:
        """Write batch failures to dead letter queue with memory safety."""
        if not failed_records:
            return

        os.makedirs(os.path.dirname(settings.DEAD_LETTER_FILE), exist_ok=True)

        try:
            with open(settings.DEAD_LETTER_FILE, "a", encoding="utf-8") as f:
                # LIMIT to 50 records per batch to prevent memory issues
                for record in failed_records[:50]:
                    safe_record = {
                        "timestamp": datetime.now().isoformat(),
                        "type": record.get("type", "unknown"),
                        "label": record.get("label", "unknown"),
                        "error": str(record.get("error", ""))[:200],
                        "record_sample": {k: str(v)[:100] for k, v in record.get("record", {}).items()}
                    }
                    f.write(json.dumps(safe_record) + "\n")
        except Exception as e:
            # Don't let dead letter writing break the pipeline
            logger.error(f"Failed to write batch dead letters: {e}")

    @retry(
        wait=wait_exponential(multiplier=2, min=2, max=60),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(ServiceUnavailable) |
              retry_if_exception_type(TransientError) |
              retry_if_exception_type(DatabaseError) |
              retry_if_exception_type(ClientError),
        reraise=False,
        before_sleep=lambda retry_state: logger.warning(
            f"Retrying batch after {retry_state.attempt_number} attempts. "
            f"Sleeping {retry_state.next_action.sleep} seconds."
        )
    )
    def _execute_query_batch(self, query: str, data: List[Dict[str, Any]], label: str) -> Tuple[int, List[Dict]]:
        """
        Execute query batch with retry logic.
        Returns: (created_count, failed_records)
        """
        if not data:
            return 0, []

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

                self._adjust_batch_size(True)
                return created, []

        except Exception as e:
            logger.error(
                "Error loading batch: %s | Size: %d | Error: %s",
                label, len(data), str(e)[:200]
            )

            self._adjust_batch_size(False)

            # Return failed records for dead letter queue
            failed_records = []
            for record in data[:5]:  # Only sample first 5 records
                failed_records.append({
                    "type": "batch_failure",
                    "label": label,
                    "error": str(e)[:200],
                    "record": {k: str(v)[:100] for k, v in record.items()}
                })

            self.total_failed_records += len(data)
            return 0, failed_records

    # ----------------------------
    # Node loaders (updated for immediate relationship creation)
    # ----------------------------

    def load_states(self, states: List[Dict]) -> Tuple[int, List[Dict]]:
        if not states:
            return 0, []

        query = """
        UNWIND $data AS state
        MERGE (:State {code: state.code})
        """
        created, failed = self._execute_query_batch(query, states, "State")
        if failed:
            self._write_batch_dead_letters(failed)
        return created, failed

    def load_cities(self, cities: List[Dict]) -> Tuple[int, List[Dict]]:
        if not cities:
            return 0, []

        query = """
        UNWIND $data AS city
        MERGE (:City {name: city.name, state_code: city.state_code})
        """
        created, failed = self._execute_query_batch(query, cities, "City")
        if failed:
            self._write_batch_dead_letters(failed)
        return created, failed

    def load_postal_codes(self, postal_codes: List[Dict]) -> Tuple[int, List[Dict]]:
        if not postal_codes:
            return 0, []

        query = """
        UNWIND $data AS pc
        MERGE (:PostalCode {code: pc.code})
        """
        created, failed = self._execute_query_batch(query, postal_codes, "PostalCode")
        if failed:
            self._write_batch_dead_letters(failed)
        return created, failed

    def load_businesses_complete(self, businesses: List[Dict[str, Any]]) -> Tuple[int, List[Dict]]:
        """
        Load businesses WITH their geographic relationships in a single operation.
        This ensures atomic creation of business with all its connections.
        """
        if not businesses:
            return 0, []

        # Split into micro-batches for memory safety
        micro_batch_size = max(50, min(100, self.current_batch_size // 2))
        total_created = 0
        total_failed = []

        for i in range(0, len(businesses), micro_batch_size):
            micro_batch = businesses[i:i + micro_batch_size]

            # Check memory pressure before each micro-batch
            if self._check_memory_pressure():
                logger.warning("Memory pressure - pausing before next micro-batch")
                time.sleep(2)
                micro_batch_size = max(self.min_batch_size, micro_batch_size // 2)

            query = """
            UNWIND $data AS b
            // Create or match Business
            MERGE (biz:Business {business_id: b.business_id})
            SET biz.name = b.name,
                biz.stars = b.stars,
                biz.review_count = b.review_count,
                biz.is_open = b.is_open

            // Create or match State (if exists)
            WITH biz, b
            WHERE b.state IS NOT NULL
            MERGE (state:State {code: b.state})
            MERGE (biz)-[:CLAIMS_STATE]->(state)

            // Create or match City (if exists) - requires both city and state
            WITH biz, b, state
            WHERE b.city IS NOT NULL AND b.state IS NOT NULL
            MERGE (city:City {name: b.city, state_code: b.state})
            MERGE (biz)-[loc:LOCATED_NEAR]->(city)
            SET loc.latitude = b.latitude,
                loc.longitude = b.longitude
            MERGE (city)-[:CLAIMS_STATE]->(state)  // City->State relationship

            // Create or match PostalCode (if exists)
            WITH biz, b
            WHERE b.postal_code IS NOT NULL
            MERGE (postal:PostalCode {code: b.postal_code})
            MERGE (biz)-[:CLAIMS_POSTAL_CODE]->(postal)
            """

            created, failed = self._execute_query_batch(query, micro_batch, "BusinessComplete")
            total_created += created
            if failed:
                total_failed.extend(failed)
                self._write_batch_dead_letters(failed)

            # Small pause between micro-batches to let Neo4j catch up
            if i + micro_batch_size < len(businesses):
                time.sleep(0.1)

        return total_created, total_failed

    def load_categories(self, categories: List[Dict[str, Any]]) -> Tuple[int, List[Dict]]:
        if not categories:
            return 0, []

        query = """
        UNWIND $data AS cat
        MERGE (:Category {name: cat.name})
        """
        created, failed = self._execute_query_batch(query, categories, "Category")
        if failed:
            self._write_batch_dead_letters(failed)
        return created, failed

    def load_reviews(self, reviews: List[Dict[str, Any]]) -> Tuple[int, List[Dict]]:
        if not reviews:
            return 0, []

        # Split into smaller batches for reviews (they're text-heavy)
        micro_batch_size = max(50, min(100, self.current_batch_size // 2))
        total_created = 0
        total_failed = []

        for i in range(0, len(reviews), micro_batch_size):
            micro_batch = reviews[i:i + micro_batch_size]

            query = """
            UNWIND $data AS r
            MERGE (rev:Review {review_id: r.review_id})
            SET rev.user_id = r.user_id,
                rev.business_id = r.business_id,
                rev.stars = r.stars,
                rev.date = r.date,
                rev.useful = r.useful,
                rev.funny = r.funny,
                rev.cool = r.cool
            """
            created, failed = self._execute_query_batch(query, micro_batch, "Review")
            total_created += created
            if failed:
                total_failed.extend(failed)

            # Small pause
            if i + micro_batch_size < len(reviews):
                time.sleep(0.05)

        if total_failed:
            self._write_batch_dead_letters(total_failed)
        return total_created, total_failed

    def load_users(self, users: List[Dict]) -> Tuple[int, List[Dict]]:
        if not users:
            return 0, []

        query = """
        UNWIND $data AS u
        MERGE (user:User {user_id: u.user_id})
        SET user.name = u.name,
            user.review_count = u.review_count,
            user.yelping_since = u.yelping_since,
            user.useful = u.useful,
            user.funny = u.funny,
            user.cool = u.cool,
            user.fans = u.fans,
            user.average_stars = u.average_stars,
            user.compliment_hot = u.compliment_hot,
            user.compliment_more = u.compliment_more,
            user.compliment_profile = u.compliment_profile,
            user.compliment_cute = u.compliment_cute,
            user.compliment_list = u.compliment_list,
            user.compliment_note = u.compliment_note,
            user.compliment_plain = u.compliment_plain,
            user.compliment_cool = u.compliment_cool,
            user.compliment_funny = u.compliment_funny,
            user.compliment_writer = u.compliment_writer,
            user.compliment_photos = u.compliment_photos
        """
        created, failed = self._execute_query_batch(query, users, "Users")
        if failed:
            self._write_batch_dead_letters(failed)
        return created, failed

    # ----------------------------
    # Relationship loaders (for non-business relationships)
    # ----------------------------

    def create_relationships(self, relationships: List[Dict[str, Any]]) -> Tuple[int, List[Dict]]:
        if not relationships:
            return 0, []

        total_created = 0
        total_failed = []
        grouped: Dict[str, List[Dict[str, Any]]] = {}

        for rel in relationships:
            grouped.setdefault(rel["relationship_type"], []).append(rel)

        for rel_type, rels in grouped.items():
            # Process relationships in smaller chunks
            chunk_size = max(100, min(200, self.current_batch_size // 3))

            for i in range(0, len(rels), chunk_size):
                chunk = rels[i:i + chunk_size]

                if rel_type == "WROTE":
                    query = """
                    UNWIND $data AS r
                    MATCH (u:User {user_id: r.from_node_id_value})
                    MATCH (rev:Review {review_id: r.to_node_id_value})
                    MERGE (u)-[:WROTE]->(rev)
                    """
                elif rel_type == "OF":
                    query = """
                    UNWIND $data AS r
                    MATCH (rev:Review {review_id: r.from_node_id_value})
                    MATCH (b:Business {business_id: r.to_node_id_value})
                    MERGE (rev)-[:OF]->(b)
                    """
                elif rel_type == "CLAIMS_CATEGORY":
                    query = """
                    UNWIND $data AS r
                    MATCH (b:Business {business_id: r.from_node_id_value})
                    MATCH (cat:Category {name: r.to_node_id_value})
                    MERGE (b)-[:CLAIMS_CATEGORY]->(cat)
                    """
                elif rel_type == "FRIENDS_WITH":
                    query = """
                    UNWIND $data AS r
                    MATCH (u1:User {user_id: r.from_node_id_value})
                    MATCH (u2:User {user_id: r.to_node_id_value})
                    MERGE (u1)-[:FRIENDS_WITH]->(u2)
                    """
                else:
                    logger.warning(f"Unknown relationship type: {rel_type}")
                    continue

                created, failed = self._execute_query_batch(query, chunk, rel_type)
                total_created += created
                if failed:
                    total_failed.extend(failed)

                # Small pause between relationship chunks
                if i + chunk_size < len(rels):
                    time.sleep(0.05)

        if total_failed:
            self._write_batch_dead_letters(total_failed)

        return total_created, total_failed