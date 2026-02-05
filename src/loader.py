from neo4j import GraphDatabase, Driver, Address
from neo4j.exceptions import ServiceUnavailable, TransientError, DatabaseError, ClientError
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from typing import List, Dict, Any, Tuple
import time
import os
import json
from datetime import datetime
import logging
import gc
import socket
import threading  # Added threading import

from src.settings import settings
from src.dead_letter_handler import write_batch_failure_dead_letter

logger = logging.getLogger(__name__)


class Neo4jLoader:
    def ipv4_resolver(self, address):
        """
        A custom resolver function that forces the use of IPv4 addresses.
        It resolves the hostname to IPv4 addresses and yields them.
        """
        try:
            addr_info = socket.getaddrinfo(address.host, address.port, socket.AF_INET, socket.SOCK_STREAM)
            for family, socktype, proto, canonname, sockaddr in addr_info:
                yield Address((sockaddr[0], address.port))
        except socket.gaierror as e:
            logger.error(f"Could not resolve address {address.host}:{address.port} to IPv4: {e}")
            raise

    def __init__(self):
        try:
            self.driver: Driver = GraphDatabase.driver(
                settings.NEO4J_URI, 
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                resolver=self.ipv4_resolver # Pass the custom resolver here
            )
            self._verify_connection()
            logger.warning("Neo4j driver initialized and connected.")
            self._create_constraints_and_indexes()
            logger.warning("Neo4j constraints and indexes ensured.")

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
        logger.warning("Entering Neo4jLoader context.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        if exc_type:
            logger.error(f"Exited Neo4jLoader context with an exception: {exc_val}", exc_info=True)
        else:
            logger.warning("Exited Neo4jLoader context gracefully.")

    def close(self):
        if self.driver:
            self.driver.close()
            logger.warning("Neo4j driver closed.")

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(ServiceUnavailable),
        reraise=True
    )
    def _verify_connection(self):
        logger.warning("Attempting to verify Neo4j connectivity...")
        self.driver.verify_connectivity()
        logger.warning("Neo4j connectivity verified.")

    def _create_constraints_and_indexes(self):
        """Creates constraints and indexes defined in settings."""
        with self.driver.session() as session:
            for query in settings.NEO4J_CONSTRAINTS_AND_INDEXES:
                try:
                    session.run(query)
                    logger.warning(f"Executed constraint/index query: {query}")
                except Exception as e:
                    logger.error(f"Failed to execute constraint/index query '{query}': {e}", exc_info=True)
                    # Depending on severity, you might want to reraise here or just log
                    raise

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

    def _sanitize_cypher_identifier(self, identifier: str, context: str) -> str:
        """
        Sanitizes a string to be a valid Cypher identifier (label, relationship type, property name).
        Allowed characters are alphanumeric and underscores. Cannot start with a digit.
        """
        if not identifier:
            raise ValueError(f"Cypher identifier cannot be empty. Context: {context}")

        # Check for valid characters: alphanumeric and underscore
        if not all(c.isalnum() or c == '_' for c in identifier):
            raise ValueError(f"Invalid characters in Cypher identifier '{identifier}'. Only alphanumeric and "
                             f"underscores are allowed. Context: {context}")

        # Cannot start with a digit
        if identifier[0].isdigit():
            raise ValueError(f"Cypher identifier '{identifier}' cannot start with a digit. Context: {context}")

        return identifier

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

        logger.debug(f"Executing batch for label '{label}' with {len(data)} records. First record type: {type(data[0]) if data else 'N/A'}")
        if label == "OF": # TEMP DEBUG
            logger.debug(f"OF Query: {query}") # TEMP DEBUG
            logger.debug(f"OF Data Sample: {data[:2]}") # TEMP DEBUG
        logger.debug(f"First 2 data records: {data[:2]}")

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
                    "%s batch executed | nodes_created=%d | rels_created=%d | props_set=%d",
                    label,
                    counters.nodes_created,
                    counters.relationships_created,
                    counters.properties_set,
                )

                self._adjust_batch_size(True)
                return created, []

        except Exception as e:
            logger.error(
                "Error loading batch: %s | Size: %d | Error: %s",
                label, len(data), str(e)[:200]
            )

            self._adjust_batch_size(False)

            self.total_failed_records += len(data)
            return 0, data # Return all records as failed, not just a sample

    # ----------------------------
    # Node loaders (updated for immediate relationship creation)
    # ----------------------------



    def load_nodes(self, nodes: List[Dict[str, Any]], node_label: str, id_property: str) -> Tuple[int, List[Dict]]:
        if not nodes:
            return 0, []

        # Sanitize node_label and id_property using the dedicated helper
        sanitized_node_label = self._sanitize_cypher_identifier(node_label, "node_label in load_nodes")
        sanitized_id_property = self._sanitize_cypher_identifier(id_property, "id_property in load_nodes")

        query = f"""
        UNWIND $data AS node_data
        MERGE (n:{sanitized_node_label} {{ {sanitized_id_property}: node_data.{sanitized_id_property} }})
        SET n += node_data
        """

        created, failed = self._execute_query_batch(query, nodes, node_label)
        if failed:
            write_batch_failure_dead_letter(
                failed_records=failed,
                record_type="node_load_failure",
                label=node_label,
                error_message="Failed to load node(s)"
            )
        return created, failed



    # ----------------------------
    # Relationship loaders (for non-business relationships)
    # ----------------------------

    def load_relationships(self, relationships: List[Dict[str, Any]]) -> Tuple[int, List[Dict]]:
        if not relationships:
            return 0, []

        total_created = 0
        total_failed = []
        grouped: Dict[str, List[Dict[str, Any]]] = {}

        for rel in relationships:
            grouped.setdefault(rel["relationship_type"], []).append(rel)

        # Define relationship query templates
        REL_QUERY_TEMPLATES = {
            "WROTE": """
                UNWIND $data AS r
                MATCH (u:User {user_id: r.from_node_id_value})
                MATCH (rev:Review {review_id: r.to_node_id_value})
                MERGE (u)-[w:WROTE]->(rev)
                SET u += r.from_node_properties, rev += r.to_node_properties, w += r.properties
            """,
            "OF": """
                UNWIND $data AS r
                MATCH (rev:Review {review_id: r.from_node_id_value})
                MATCH (b:Business {business_id: r.to_node_id_value})
                MERGE (rev)-[o:OF]->(b)
                SET rev += r.from_node_properties, b += r.to_node_properties, o += r.properties
            """,
            "CLAIMS_CATEGORY": """
                UNWIND $data AS r
                MATCH (b:Business {business_id: r.from_node_id_value})
                MATCH (cat:Category {name: r.to_node_id_value})
                MERGE (b)-[c:CLAIMS_CATEGORY]->(cat)
                SET b += r.from_node_properties, cat += r.to_node_properties, c += r.properties
            """,
            "FRIENDS_WITH": """
                UNWIND $data AS r
                MATCH (u1:User {user_id: r.from_node_id_value})
                MATCH (u2:User {user_id: r.to_node_id_value})
                MERGE (u1)-[f:FRIENDS_WITH]->(u2)
                SET u1 += r.from_node_properties, u2 += r.to_node_properties, f += r.properties
            """,
            "IN": """
                UNWIND $data AS r
                MATCH (city:City {name: r.from_node_id_value, state_code: r.from_node_id_aux_value})
                MERGE (state:State {code: r.to_node_id_value})
                OPTIONAL MATCH (city)-[old:IN]->(s) WHERE s <> state
                DELETE old
                MERGE (city)-[isi:IN]->(state)
                SET city += r.from_node_properties, state += r.to_node_properties, isi += r.properties
            """,
            "LOCATED_NEAR": """
                UNWIND $data AS r
                MATCH (b:Business {business_id: r.from_node_id_value})
                MATCH (city:City {name: r.to_node_id_value, state_code: r.to_node_id_aux_value})
                MERGE (b)-[ln:LOCATED_NEAR]->(city)
                SET b += r.from_node_properties, city += r.to_node_properties, ln += r.properties
            """,
            "CLAIMS_STATE": """
                UNWIND $data AS r
                MATCH (b:Business {business_id: r.from_node_id_value})
                MERGE (s:State {code: r.to_node_id_value})
                MERGE (b)-[cs:CLAIMS_STATE]->(s)
                SET b += r.from_node_properties, s += r.to_node_properties, cs += r.properties
            """,
            "CLAIMS_POSTAL_CODE": """
                UNWIND $data AS r
                MATCH (b:Business {business_id: r.from_node_id_value})
                MATCH (pc:PostalCode {code: r.to_node_id_value})
                MERGE (b)-[cp:CLAIMS_POSTAL_CODE]->(pc)
                SET b += r.from_node_properties, pc += r.to_node_properties, cp += r.properties
            """,
            # Add other relationship types as needed
        }

        for rel_type, rels in grouped.items():
            query_template = REL_QUERY_TEMPLATES.get(rel_type)
            if not query_template:
                logger.warning(f"Unknown relationship type encountered and skipped: {rel_type}")
                total_failed.extend(rels) # Consider all skipped relationships as failed for dead-lettering
                continue

            # Process relationships in smaller chunks
            chunk_size = max(100, min(200, self.current_batch_size // 3))

            for i in range(0, len(rels), chunk_size):
                chunk = rels[i:i + chunk_size]

                # Extract relationship properties and node properties if they exist in the chunk
                # This assumes normalizer will add 'from_node_properties', 'to_node_properties', 'properties'
                # if there are dynamic properties to set on nodes/relationships themselves.
                # For now, default to empty dicts if not present.
                processed_chunk = []
                for item in chunk:
                    processed_item = item.copy()
                    processed_item.setdefault('from_node_properties', {})
                    processed_item.setdefault('to_node_properties', {})
                    processed_item.setdefault('properties', {})
                    processed_chunk.append(processed_item)


                created, failed = self._execute_query_batch(query_template, processed_chunk, rel_type)
                total_created += created
                if failed:
                    total_failed.extend(failed)

                # Small pause between relationship chunks
                if i + chunk_size < len(rels):
                    time.sleep(0.05)

        if total_failed:
            write_batch_failure_dead_letter(
                failed_records=total_failed,
                record_type="relationship_load_failure",
                label="Multiple_Relationship_Types", # Can refine this if needed
                error_message="Failed to load one or more relationships"
            )

        return total_created, total_failed

    def _run_apoc_job(
        self,
        session,
        cypher: str,
        job_name_prefix: str,
        timeout_seconds: int,
        poll_interval_seconds: int
    ) -> Tuple[int, int, List[str]]:
        job_name = f"{job_name_prefix}_{int(time.time())}"
        submit_query = "CALL apoc.periodic.submit($name, $cypher) YIELD name RETURN name"
        submit_result = session.run(submit_query, name=job_name, cypher=cypher).single()
        if not submit_result or not submit_result.get("name"):
            raise RuntimeError(f"Failed to submit APOC job '{job_name_prefix}'.")

        start_time = time.time()
        last_log_time = 0.0
        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                session.run("CALL apoc.periodic.cancel($name)", name=job_name)
                raise TimeoutError(f"APOC job '{job_name}' timed out after {timeout_seconds} seconds.")

            status_rows = session.run("CALL apoc.periodic.list()").data()
            status = next((row for row in status_rows if row.get("name") == job_name), None)

            if not status:
                time.sleep(poll_interval_seconds)
                continue

            done = bool(status.get("done"))
            cancelled = bool(status.get("cancelled"))
            update_stats = status.get("updateStatistics") or status.get("updateStats") or {}

            if done or cancelled:
                batches = update_stats.get("batches") or update_stats.get("batchCount") or 0
                total = update_stats.get("total") or update_stats.get("rows") or update_stats.get("updates") or 0
                return int(batches), int(total), []

            if elapsed - last_log_time >= 30:
                last_log_time = elapsed
                logger.warning(
                    f"APOC job '{job_name_prefix}' in progress... Elapsed: {int(elapsed)}s"
                )

            time.sleep(poll_interval_seconds)

    def load_friend_relationships_apoc(
        self,
        csv_file_name: str,
        async_mode: bool = True,
        timeout_seconds: int = 300,
        poll_interval_seconds: int = 5
    ) -> Tuple[int, int, List[str]]:
        """
        Loads FRIENDS_WITH relationships using Neo4j's LOAD CSV and apoc.periodic.iterate.
        This method offloads matching and relationship creation to the Neo4j server,
        optimizing for large relationship files like user_friendship.csv.

        Args:
            csv_file_name: The name of the CSV file (e.g., "user_friendship.csv")
                           which must be accessible in Neo4j's import directory.
                           Assumes the CSV has 'user1' and 'user2' headers.

        Returns:
            A tuple containing:
                - total_batches: Number of batches processed by apoc.periodic.iterate.
                - total_rels: Total number of relationships created (best-effort for async).
                - error_messages: Any error messages reported by apoc.periodic.iterate.
        """
        neo4j_csv_path = settings.neo4j_file_url(csv_file_name)

        # Revert to direct APOC load and keep batch size small to reduce memory pressure.
        apoc_batch_size = 10

        apoc_query = f"""
        CALL apoc.periodic.iterate(
            "LOAD CSV WITH HEADERS FROM '{neo4j_csv_path}' AS row
             WITH row
             WHERE row.user1 IS NOT NULL AND row.user2 IS NOT NULL AND row.user1 <> row.user2
             RETURN row",
            "MATCH (u1:User {{user_id: row.user1}}) USING INDEX u1:User(user_id)
             MATCH (u2:User {{user_id: row.user2}}) USING INDEX u2:User(user_id)
             MERGE (u1)-[:FRIENDS_WITH]->(u2)",
            {{batchSize: {apoc_batch_size}, parallel: false, iterateList: true, retries: 5}}
        ) YIELD batches, total, errorMessages
        RETURN batches, total, errorMessages
        """

        logger.warning(f"Initiating server-side loading for friends from {csv_file_name} using APOC.")
        
        try:
            with self.driver.session() as session:
                if not async_mode:
                    result = session.run(apoc_query).single()
                    if result["errorMessages"]:
                        logger.error(f"APOC errors for {csv_file_name}: {result['errorMessages']}")

                    batches = result["batches"]
                    total = result["total"]
                    errors = result["errorMessages"]

                    logger.warning(f"Server-side friend loading complete for {csv_file_name}: "
                                f"Batches: {batches}, Relationships Created: {total}")
                    return batches, total, errors

                batches, total, errors = self._run_apoc_job(
                    session,
                    apoc_query,
                    "apoc_friend_load",
                    timeout_seconds,
                    poll_interval_seconds
                )
                logger.warning(
                    f"Server-side friend loading complete for {csv_file_name}: "
                    f"Batches: {batches}, Relationships Created: {total}"
                )
                return batches, total, errors

        except Exception as e:
            logger.error(f"Failed server-side friend loading for {csv_file_name}: {e}", exc_info=True)
            raise
