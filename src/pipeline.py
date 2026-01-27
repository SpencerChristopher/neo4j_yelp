import logging
import os
import json
import pandas as pd
from typing import Optional
import time
import gc

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
from src.settings import settings

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


def verify_data_integrity(loader):
    """Perform comprehensive data integrity checks."""
    checks = [
        ("Total nodes", "MATCH (n) RETURN count(n) as total_nodes"),
        ("Total relationships", "MATCH ()-[r]->() RETURN count(r) as total_rels"),

        # Review count validation
        ("Business review count mismatches", """
            MATCH (b:Business)
            OPTIONAL MATCH (b)<-[:OF]-(r:Review)
            WITH b, b.review_count as expected, count(r) as actual
            WHERE expected IS NOT NULL AND expected != actual
            RETURN count(b) as mismatched_count
        """),

        # Orphaned reviews check
        ("Orphaned reviews (no user)", """
            MATCH (r:Review)
            WHERE NOT (r)<-[:WROTE]-()
            RETURN count(r) as orphaned_reviews
        """),

        # Orphaned reviews check (no business)
        ("Orphaned reviews (no business)", """
            MATCH (r:Review)
            WHERE NOT (r)-[:OF]->()
            RETURN count(r) as orphaned_reviews
        """),

        # Users without reviews
        ("Users without reviews", """
            MATCH (u:User)
            WHERE NOT (u)-[:WROTE]->()
            RETURN count(u) as users_without_reviews
        """),

        # Businesses without categories
        ("Businesses without categories", """
            MATCH (b:Business)
            WHERE NOT (b)-[:CLAIMS_CATEGORY]->()
            RETURN count(b) as businesses_without_categories
        """),
    ]

    with loader.driver.session() as session:
        for check_name, query in checks:
            try:
                result = session.run(query).single()
                if result:
                    value = result[0]
                    if "mismatch" in check_name.lower() or "orphaned" in check_name.lower():
                        if value > 0:
                            logger.warning(f"INTEGRITY CHECK: {check_name}: {value}")
                        else:
                            logger.info(f"INTEGRITY CHECK: {check_name}: {value} ✓")
                    else:
                        logger.info(f"INTEGRITY CHECK: {check_name}: {value}")
            except Exception as e:
                logger.error(f"Failed integrity check '{check_name}': {e}")


def validate_review_counts(loader, sample_size=100):
    """
    Validate that business.review_count matches actual connected reviews.
    Logs details for mismatches.
    """
    query = """
    MATCH (b:Business)
    WHERE b.review_count > 0
    WITH b
    OPTIONAL MATCH (b)<-[:OF]-(r:Review)
    WITH b, b.review_count as expected, count(r) as actual
    WHERE expected != actual
    RETURN b.business_id, b.name, expected, actual
    LIMIT $sample_size
    """

    with loader.driver.session() as session:
        mismatches = session.run(query, sample_size=sample_size).data()

        if mismatches:
            logger.warning(f"Found {len(mismatches)} businesses with mismatched review counts")
            for mismatch in mismatches[:10]:  # Log first 10
                logger.warning(f"  Business: {mismatch['b.name']} (ID: {mismatch['b.business_id']})")
                logger.warning(f"    Expected: {mismatch['expected']}, Actual: {mismatch['actual']}")

            # Summary statistics
            total_discrepancy = sum(abs(m['expected'] - m['actual']) for m in mismatches)
            logger.warning(f"Total review count discrepancy across sampled businesses: {total_discrepancy}")
        else:
            logger.info("✓ All business review counts match connected reviews")

        return len(mismatches)


def run_pipeline(max_batches: Optional[int] = None):
    """Main ETL pipeline with optimal loading order and immediate relationship creation."""

    stats = PipelineStats()
    logger.info("Starting Yelp ETL pipeline with optimal loading order")

    # Initialize dead letter queue
    os.makedirs(os.path.dirname(settings.DEAD_LETTER_FILE), exist_ok=True)
    with open(settings.DEAD_LETTER_FILE, "w") as f:
        f.write("")  # Clear file

    try:
        with Neo4jLoader(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD) as loader:

            # --- PHASE 1: User Nodes (NO relationships yet) ---
            stats.log_phase_start("Phase 1: Users")
            user_path = settings.DATA_DIR / settings.USER_CSV

            if not os.path.exists(user_path):
                logger.error(f"User CSV not found: {user_path}")
                return

            logger.info("Loading User nodes (Phase 1 of 5)...")

            user_chunk_size = 500
            user_iter = pd.read_csv(user_path, chunksize=user_chunk_size)

            for batch_num, chunk in enumerate(user_iter, start=1):
                if max_batches and batch_num > max_batches:
                    break

                stats.total_rows_processed += len(chunk)
                raw_records = chunk.replace({float('nan'): None}).to_dict(orient="records")
                valid, invalid = validate_user_data(raw_records)
                stats.validation_failures += len(invalid)
                _write_dead_letters(invalid)

                if not valid:
                    continue

                user_nodes = normalize_user_data(valid)
                created, failed = loader.load_users(user_nodes)

                if failed:
                    stats.failed_batches += 1
                    stats.batch_failures += len(failed)
                else:
                    stats.successful_batches += 1

                # Clean memory
                if batch_num % 20 == 0:
                    gc.collect()
                    logger.debug(f"Loaded {batch_num * user_chunk_size} users so far")

            logger.info("User nodes loaded.")
            stats.log_phase_end("Phase 1: Users")

            # --- PHASE 2: Business Nodes with Immediate Geographic Relationships ---
            stats.log_phase_start("Phase 2: Businesses with Geographic Relationships")
            business_path = settings.DATA_DIR / settings.BUSINESS_CSV

            if not os.path.exists(business_path):
                logger.error(f"Business CSV not found: {business_path}")
                return

            logger.info("Loading businesses with immediate geographic relationships (Phase 2 of 5)...")

            business_chunk_size = 200
            business_iter = pd.read_csv(business_path, chunksize=business_chunk_size)

            for batch_num, chunk in enumerate(business_iter, start=1):
                if max_batches and batch_num > max_batches:
                    break

                stats.total_rows_processed += len(chunk)
                logger.debug(f"Processing business batch {batch_num} ({len(chunk)} records)")

                raw_records = chunk.replace({float('nan'): None}).to_dict(orient="records")

                # Debug: Check first record
                if batch_num == 1 and raw_records:
                    first_record = raw_records[0]
                    logger.debug(f"First business record: business_id={first_record.get('business_id')}, "
                                 f"state='{first_record.get('state')}', city='{first_record.get('city')}'")

                # Validate
                valid, invalid = validate_business_data(raw_records)
                stats.validation_failures += len(invalid)
                _write_dead_letters(invalid)

                if not valid:
                    logger.warning(f"Batch {batch_num}: No valid records after validation")
                    continue

                # Normalize
                bus_nodes, state_nodes, city_nodes, postal_code_nodes, geo_rels = normalize_business_data(valid)

                logger.info(f"Batch {batch_num}: Normalized - {len(bus_nodes)} businesses, "
                            f"{len(state_nodes)} states, {len(city_nodes)} cities, "
                            f"{len(postal_code_nodes)} postal codes")

                # Load businesses WITH geographic relationships in one operation
                if bus_nodes:
                    created_business, failed_business = loader.load_businesses_complete(bus_nodes)

                    if created_business:
                        logger.info(f"Created {created_business} businesses with relationships")
                        stats.successful_batches += 1
                    else:
                        logger.warning(f"Batch {batch_num}: Failed to create businesses")
                        stats.failed_batches += 1

                    if failed_business:
                        logger.error(f"Batch {batch_num}: {len(failed_business)} business records failed")
                        stats.batch_failures += len(failed_business)

                # Clean up memory
                del raw_records, valid, bus_nodes, state_nodes, city_nodes, postal_code_nodes, geo_rels
                if batch_num % 10 == 0:
                    gc.collect()
                    logger.debug(f"Processed {batch_num * business_chunk_size} businesses so far")

            logger.info("Business nodes with geographic relationships loaded.")
            stats.log_phase_end("Phase 2: Businesses with Geographic Relationships")

            # --- PHASE 3: Category Nodes and Business-Category Relationships ---
            stats.log_phase_start("Phase 3: Categories and Business-Category Relationships")
            category_path = settings.DATA_DIR / settings.CATEGORY_CSV

            if not os.path.exists(category_path):
                logger.error(f"Category CSV not found: {category_path}")
                return

            logger.info("Loading categories and business-category relationships (Phase 3 of 5)...")

            category_chunk_size = 1000
            category_iter = pd.read_csv(category_path, chunksize=category_chunk_size)

            for batch_num, chunk in enumerate(category_iter, start=1):
                if max_batches and batch_num > max_batches:
                    break

                stats.total_rows_processed += len(chunk)
                raw_records = chunk.replace({float('nan'): None}).to_dict(orient="records")
                valid, invalid = validate_category_data(raw_records)
                stats.validation_failures += len(invalid)
                _write_dead_letters(invalid)

                if not valid:
                    continue

                cat_nodes, cat_rels = normalize_category_data(valid)

                # Load category nodes
                if cat_nodes:
                    created_cats, failed_cats = loader.load_categories(cat_nodes)

                # Load business-category relationships
                if cat_rels:
                    created_rels, failed_rels = loader.create_relationships(cat_rels)
                    stats.total_rels_created += created_rels

                    if failed_rels:
                        stats.failed_batches += 1
                        stats.batch_failures += len(failed_rels)
                    else:
                        stats.successful_batches += 1

            logger.info("Category nodes and business-category relationships loaded.")
            stats.log_phase_end("Phase 3: Categories and Business-Category Relationships")

            # --- PHASE 4: Review Nodes with Immediate Relationships ---
            stats.log_phase_start("Phase 4: Reviews with Immediate User/Business Relationships")
            review_path = settings.DATA_DIR / settings.REVIEW_CSV

            if not os.path.exists(review_path):
                logger.error(f"Review CSV not found: {review_path}")
                return

            logger.info("Loading review nodes with immediate relationships (Phase 4 of 5)...")

            review_chunk_size = 300
            review_iter = pd.read_csv(review_path, chunksize=review_chunk_size)

            for batch_num, chunk in enumerate(review_iter, start=1):
                if max_batches and batch_num > max_batches:
                    break

                stats.total_rows_processed += len(chunk)
                raw_records = chunk.replace({float('nan'): None}).to_dict(orient="records")

                # Debug: Check first review
                if batch_num == 1 and raw_records:
                    first_review = raw_records[0]
                    logger.debug(f"First review: review_id={first_review.get('review_id')}, "
                                 f"user_id={first_review.get('user_id')}, "
                                 f"business_id={first_review.get('business_id')}")

                valid, invalid = validate_review_data(raw_records)
                stats.validation_failures += len(invalid)
                _write_dead_letters(invalid)

                if not valid:
                    continue

                review_nodes, wrote_rels, of_rels = normalize_review_data(valid)

                # Load reviews (just nodes)
                created_reviews, failed_reviews = loader.load_reviews(review_nodes)

                # Create WROTE relationships (User→Review) - USERS MUST EXIST
                if wrote_rels:
                    created_wrote, failed_wrote = loader.create_relationships(wrote_rels)
                    if created_wrote:
                        stats.total_rels_created += created_wrote
                        logger.debug(f"Created {created_wrote} WROTE relationships")

                # Create OF relationships (Review→Business) - BUSINESSES MUST EXIST
                if of_rels:
                    created_of, failed_of = loader.create_relationships(of_rels)
                    if created_of:
                        stats.total_rels_created += created_of
                        logger.debug(f"Created {created_of} OF relationships")

                if any([failed_reviews, failed_wrote, failed_of]):
                    stats.failed_batches += 1
                    stats.batch_failures += sum([len(f) for f in [failed_reviews, failed_wrote, failed_of] if f])
                else:
                    stats.successful_batches += 1

                # Clean memory
                del raw_records, valid, review_nodes, wrote_rels, of_rels
                if batch_num % 15 == 0:
                    gc.collect()
                    logger.debug(f"Processed {batch_num * review_chunk_size} reviews so far")

            logger.info("Review nodes with relationships loaded.")
            stats.log_phase_end("Phase 4: Reviews with Immediate User/Business Relationships")

            # --- PHASE 5: Friend Relationships ---
            stats.log_phase_start("Phase 5: Friend Relationships")

            logger.info("Loading friend relationships (Phase 5 of 5)...")
            friend_path = settings.DATA_DIR / settings.FRIEND_CSV

            if not os.path.exists(friend_path):
                logger.error(f"Friend CSV not found: {friend_path}")
                return

            friend_iter = pd.read_csv(friend_path, chunksize=500)

            for batch_num, chunk in enumerate(friend_iter, start=1):
                if max_batches and batch_num > max_batches:
                    break

                stats.total_rows_processed += len(chunk)
                raw_records = chunk.replace({float('nan'): None}).to_dict(orient="records")
                valid, invalid = validate_friend_data(raw_records)
                stats.validation_failures += len(invalid)
                _write_dead_letters(invalid)

                if not valid:
                    continue

                friend_rels = normalize_friend_data(valid)
                created, failed = loader.create_relationships(friend_rels)
                stats.total_rels_created += created

                if failed:
                    stats.failed_batches += 1
                    stats.batch_failures += len(failed)
                else:
                    stats.successful_batches += 1

                if batch_num % 10 == 0:
                    logger.debug(f"Processed {batch_num * 500} friend relationships so far")

            logger.info("Friend relationships loaded.")
            stats.log_phase_end("Phase 5: Friend Relationships")

            # --- FINAL VERIFICATION ---
            logger.info("Performing final data integrity checks...")
            verify_data_integrity(loader)

            # Optional: Detailed review count validation
            logger.info("Validating review counts...")
            validate_review_counts(loader, sample_size=1000)

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
          Relationships Created: {summary['total_rels_created']}

        Phase Breakdown:
        """)

        for phase, phase_data in summary['phases'].items():
            duration = phase_data.get('duration', 0)
            logger.info(f"  {phase}: {duration:.2f}s")

        # Write statistics to file
        with open("logs/pipeline_stats.json", "w") as f:
            json.dump(summary, f, indent=2)

        logger.info("ETL pipeline finished successfully")


def _write_dead_letters(records):
    """Write validation errors to dead letter queue with truncation for memory safety."""
    if not records:
        return

    MAX_RECORDS_PER_BATCH = 500  # Reduced from 1000
    records_to_write = records[:MAX_RECORDS_PER_BATCH]

    with open(settings.DEAD_LETTER_FILE, "a", encoding="utf-8") as f:
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