import logging
import os
import json
import pandas as pd
from typing import Optional
import time

from src.validator import (
    validate_business_data,
    validate_user_data,
    validate_category_data,
    validate_review_data,
    validate_friend_data,
)
from src.normalizer import (
    normalize_business_data,
    normalize_user_data,
    normalize_category_data,
    normalize_review_data,
    normalize_friend_data,
)
from src.loader import Neo4jLoader
from src.settings import (
    DATA_DIR,
    BUSINESS_CSV,
    USER_CSV,
    CATEGORY_CSV,
    REVIEW_CSV,
    FRIEND_CSV,
    BATCH_SIZE,
    DEAD_LETTER_FILE,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
)

# Setup logging first
from src.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class PipelineStats:
    """Track pipeline statistics for monitoring and reporting."""

    def __init__(self):
        self.start_time = time.time()
        self.successful_batches = 0
        self.failed_batches = 0
        self.validation_failures = 0
        self.batch_failures = 0
        self.total_rows_processed = 0
        self.total_nodes_created = 0
        self.total_rels_created = 0
        self.phase_stats = {}

    def log_phase_start(self, phase_name):
        self.phase_stats[phase_name] = {"start": time.time()}
        logger.info(f"=== STARTING PHASE: {phase_name} ===")

    def log_phase_end(self, phase_name, nodes_created=0, rels_created=0):
        if phase_name in self.phase_stats:
            duration = time.time() - self.phase_stats[phase_name]["start"]
            self.phase_stats[phase_name]["duration"] = duration
            self.phase_stats[phase_name]["nodes"] = nodes_created
            self.phase_stats[phase_name]["rels"] = rels_created
            logger.info(f"=== COMPLETED PHASE: {phase_name} in {duration:.2f}s ===")

    def get_summary(self):
        total_time = time.time() - self.start_time
        return {
            "total_time_seconds": total_time,
            "successful_batches": self.successful_batches,
            "failed_batches": self.failed_batches,
            "validation_failures": self.validation_failures,
            "batch_failures": self.batch_failures,
            "total_rows_processed": self.total_rows_processed,
            "total_nodes_created": self.total_nodes_created,
            "total_rels_created": self.total_rels_created,
            "phases": self.phase_stats,
            "throughput_rows_per_sec": self.total_rows_processed / total_time if total_time > 0 else 0
        }


GEOGRAPHIC_RELATIONSHIP_TYPES = [
    "LOCATED_NEAR",
    "CLAIMS_STATE",
    "CLAIMS_POSTAL_CODE"
]


def run_pipeline(max_batches: Optional[int] = None):
    """Main ETL pipeline with enhanced error handling and statistics."""

    stats = PipelineStats()
    logger.info("Starting Yelp ETL pipeline with enhanced error handling")

    # Initialize dead letter queue
    os.makedirs(os.path.dirname(DEAD_LETTER_FILE), exist_ok=True)
    with open(DEAD_LETTER_FILE, "w") as f:
        f.write("")  # Clear file

    try:
        with Neo4jLoader(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD) as loader:

            # --- PHASE 1: Load All Base Nodes ---
            stats.log_phase_start("Phase 1: Base Nodes")

            # 1.1 Geographic and Business Nodes
            business_path = os.path.join(DATA_DIR, BUSINESS_CSV)
            logger.info("Loading Geographic and Business nodes...")

            business_iter_nodes_pass1 = pd.read_csv(business_path, chunksize=loader.current_batch_size)
            for batch_num, chunk in enumerate(business_iter_nodes_pass1, start=1):
                stats.total_rows_processed += len(chunk)
                # Convert NaN to None for Pydantic compatibility
                raw_records = chunk.replace({float('nan'): None}).to_dict(orient="records")
                valid, invalid = validate_business_data(raw_records)
                stats.validation_failures += len(invalid)
                _write_dead_letters(invalid)

                if not valid:
                    continue

                bus_nodes, state_nodes, city_nodes, postal_code_nodes, geo_rels = normalize_business_data(valid)

                # Load nodes with error handling
                try:
                    # Load nodes
                    created_states, failed_states = loader.load_states(state_nodes)
                    created_cities, failed_cities = loader.load_cities(city_nodes)
                    created_postal, failed_postal = loader.load_postal_codes(postal_code_nodes)
                    created_business, failed_business = loader.load_businesses(bus_nodes)

                    # Load City->State relationships
                    city_state_rels = [r for r in geo_rels if r.get("relationship_type") == "CLAIMS_STATE"
                                       and r.get("from_node_type") == "City"]
                    if city_state_rels:
                        created_rels, failed_rels = loader.create_relationships(city_state_rels)
                        stats.total_rels_created += created_rels

                    # Update stats
                    if any([failed_states, failed_cities, failed_postal, failed_business]):
                        stats.failed_batches += 1
                        stats.batch_failures += sum(
                            [len(f) for f in [failed_states, failed_cities, failed_postal, failed_business] if f])
                    else:
                        stats.successful_batches += 1

                except Exception as e:
                    stats.failed_batches += 1
                    logger.critical(f"CRITICAL: Business batch {batch_num} failed completely: {str(e)[:200]}")
                    # Continue with next batch instead of stopping pipeline
                    continue

            logger.info("Geographic and Business nodes loaded.")

            # 1.2 User Nodes
            user_path = os.path.join(DATA_DIR, USER_CSV)
            logger.info("Loading User nodes...")

            user_iter_nodes = pd.read_csv(user_path, chunksize=loader.current_batch_size)
            for batch_num, chunk in enumerate(user_iter_nodes, start=1):
                if max_batches and batch_num > max_batches: break

                stats.total_rows_processed += len(chunk)
                # Convert NaN to None for Pydantic compatibility
                raw_records = chunk.replace({float('nan'): None}).to_dict(orient="records")
                valid, invalid = validate_user_data(raw_records)
                stats.validation_failures += len(invalid)
                _write_dead_letters(invalid)

                if not valid: continue
                user_nodes = normalize_user_data(valid)
                created, failed = loader.load_users(user_nodes)

                if failed:
                    stats.failed_batches += 1
                    stats.batch_failures += len(failed)
                else:
                    stats.successful_batches += 1

            logger.info("User nodes loaded.")

            # 1.3 Category Nodes
            category_path = os.path.join(DATA_DIR, CATEGORY_CSV)
            logger.info("Loading Category nodes...")

            category_iter_nodes = pd.read_csv(category_path, chunksize=loader.current_batch_size)
            for batch_num, chunk in enumerate(category_iter_nodes, start=1):
                if max_batches and batch_num > max_batches: break

                stats.total_rows_processed += len(chunk)
                # Convert NaN to None for Pydantic compatibility
                raw_records = chunk.replace({float('nan'): None}).to_dict(orient="records")
                valid, invalid = validate_category_data(raw_records)
                stats.validation_failures += len(invalid)
                _write_dead_letters(invalid)

                if not valid: continue
                cat_nodes, _ = normalize_category_data(valid)
                created, failed = loader.load_categories(cat_nodes)

                if failed:
                    stats.failed_batches += 1
                    stats.batch_failures += len(failed)
                else:
                    stats.successful_batches += 1

            logger.info("Category nodes loaded.")
            stats.log_phase_end("Phase 1: Base Nodes")

            # --- PHASE 2: Review Nodes and Relationships ---
            stats.log_phase_start("Phase 2: Reviews")

            review_path = os.path.join(DATA_DIR, REVIEW_CSV)
            logger.info("Loading Review nodes and relationships...")

            review_iter_all = pd.read_csv(review_path, chunksize=loader.current_batch_size)
            for batch_num, chunk in enumerate(review_iter_all, start=1):
                if max_batches and batch_num > max_batches: break

                stats.total_rows_processed += len(chunk)
                # Convert NaN to None for Pydantic compatibility
                raw_records = chunk.replace({float('nan'): None}).to_dict(orient="records")
                valid, invalid = validate_review_data(raw_records)
                stats.validation_failures += len(invalid)
                _write_dead_letters(invalid)

                if not valid: continue
                review_nodes, wrote_rels, of_rels = normalize_review_data(valid)

                # Load reviews and relationships
                created_reviews, failed_reviews = loader.load_reviews(review_nodes)
                created_wrote, failed_wrote = loader.create_relationships(wrote_rels)
                created_of, failed_of = loader.create_relationships(of_rels)

                stats.total_rels_created += created_wrote + created_of

                if any([failed_reviews, failed_wrote, failed_of]):
                    stats.failed_batches += 1
                    stats.batch_failures += sum([len(f) for f in [failed_reviews, failed_wrote, failed_of] if f])
                else:
                    stats.successful_batches += 1

            logger.info("Review nodes and relationships loaded.")
            stats.log_phase_end("Phase 2: Reviews")

            # --- PHASE 3: Remaining Relationships ---
            stats.log_phase_start("Phase 3: Remaining Relationships")

            # 3.1 Business-Geographic Relationships
            logger.info("Loading Business-Geographic relationships...")
            business_iter_rels_geo = pd.read_csv(business_path, chunksize=loader.current_batch_size)
            for batch_num, chunk in enumerate(business_iter_rels_geo, start=1):
                if max_batches and batch_num > max_batches: break

                # Convert NaN to None for Pydantic compatibility
                raw_records = chunk.replace({float('nan'): None}).to_dict(orient="records")
                valid, invalid = validate_business_data(raw_records)
                if not valid: continue

                _, _, _, _, all_business_rels = normalize_business_data(valid)
                geographic_relationships = [
                    rel for rel in all_business_rels
                    if rel.get("relationship_type") in GEOGRAPHIC_RELATIONSHIP_TYPES
                       and rel.get("from_node_type") == "Business"  # Only Business relationships
                ]

                created, failed = loader.create_relationships(geographic_relationships)
                stats.total_rels_created += created

                if failed:
                    stats.failed_batches += 1
                    stats.batch_failures += len(failed)
                else:
                    stats.successful_batches += 1

            logger.info("Business-Geographic relationships loaded.")

            # 3.2 Business-Category Relationships
            logger.info("Loading Business-Category relationships...")
            category_iter_rels = pd.read_csv(category_path, chunksize=loader.current_batch_size)
            for batch_num, chunk in enumerate(category_iter_rels, start=1):
                if max_batches and batch_num > max_batches: break

                # Convert NaN to None for Pydantic compatibility
                raw_records = chunk.replace({float('nan'): None}).to_dict(orient="records")
                valid, invalid = validate_category_data(raw_records)
                stats.validation_failures += len(invalid)
                _write_dead_letters(invalid)

                if not valid: continue
                _, cat_rels = normalize_category_data(valid)
                created, failed = loader.create_relationships(cat_rels)
                stats.total_rels_created += created

                if failed:
                    stats.failed_batches += 1
                    stats.batch_failures += len(failed)
                else:
                    stats.successful_batches += 1

            logger.info("Business-Category relationships loaded.")

            # 3.3 User-User (Friends) Relationships
            logger.info("Loading User-User (Friends) relationships...")
            friend_path = os.path.join(DATA_DIR, FRIEND_CSV)
            friend_iter_rels = pd.read_csv(friend_path, chunksize=loader.current_batch_size)
            for batch_num, chunk in enumerate(friend_iter_rels, start=1):
                if max_batches and batch_num > max_batches: break

                stats.total_rows_processed += len(chunk)
                # Convert NaN to None for Pydantic compatibility
                raw_records = chunk.replace({float('nan'): None}).to_dict(orient="records")
                valid, invalid = validate_friend_data(raw_records)
                stats.validation_failures += len(invalid)
                _write_dead_letters(invalid)

                if not valid: continue
                friend_rels = normalize_friend_data(valid)
                created, failed = loader.create_relationships(friend_rels)
                stats.total_rels_created += created

                if failed:
                    stats.failed_batches += 1
                    stats.batch_failures += len(failed)
                else:
                    stats.successful_batches += 1

            logger.info("User-User (Friends) relationships loaded.")
            stats.log_phase_end("Phase 3: Remaining Relationships")

    except Exception as e:
        logger.critical(f"FATAL: Pipeline failed with error: {e}", exc_info=True)
        raise

    finally:
        # Log final statistics
        summary = stats.get_summary()
        logger.info(f"""
        PIPELINE COMPLETION REPORT:
        ===========================
        Total Time: {summary['total_time_seconds']:.2f} seconds
        Throughput: {summary['throughput_rows_per_sec']:.2f} rows/second

        Batches:
          Successful: {summary['successful_batches']}
          Failed: {summary['failed_batches']}

        Failures:
          Validation Errors: {summary['validation_failures']}
          Batch Processing Errors: {summary['batch_failures']}

        Totals:
          Rows Processed: {summary['total_rows_processed']}
          Nodes Created: {summary['total_nodes_created']}
          Relationships Created: {summary['total_rels_created']}

        Phase Breakdown:
        """)

        for phase, phase_data in summary['phases'].items():
            duration = phase_data.get('duration', 0)
            logger.info(f"  {phase}: {duration:.2f}s")

        # Write statistics to file
        with open("logs/pipeline_stats.json", "w") as f:
            json.dump(summary, f, indent=2)

        logger.info("ETL pipeline finished")


def _write_dead_letters(records):
    """Write validation errors to dead letter queue with truncation for memory safety."""
    if not records:
        return

    MAX_RECORDS_PER_BATCH = 1000  # Don't write more than 1000 records at once
    records_to_write = records[:MAX_RECORDS_PER_BATCH]

    with open(DEAD_LETTER_FILE, "a", encoding="utf-8") as f:
        for r in records_to_write:
            serializable_record = r.copy()

            # Process errors to make them JSON serializable
            if "errors" in serializable_record:
                errors = serializable_record["errors"]

                if isinstance(errors, Exception):
                    serializable_record["errors"] = str(errors)[:500]
                elif isinstance(errors, list):
                    processed_errors = []
                    for error_item in errors:
                        if isinstance(error_item, Exception):
                            processed_errors.append(str(error_item)[:500])
                        elif isinstance(error_item, dict):
                            # Check for nested errors
                            if "ctx" in error_item and "error" in error_item["ctx"]:
                                if isinstance(error_item["ctx"]["error"], Exception):
                                    error_item["ctx"]["error"] = str(error_item["ctx"]["error"])[:500]
                            processed_errors.append(error_item)
                        else:
                            processed_errors.append(str(error_item)[:500] if error_item else "")
                    serializable_record["errors"] = processed_errors

            # Truncate record data
            if "record" in serializable_record and isinstance(serializable_record["record"], dict):
                serializable_record["record"] = {
                    k: str(v)[:200] for k, v in serializable_record["record"].items()
                }

            f.write(json.dumps(serializable_record) + "\n")


if __name__ == "__main__":
    run_pipeline()