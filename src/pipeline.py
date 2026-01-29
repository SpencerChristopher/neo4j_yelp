import logging
import os
import json
import pandas as pd
from typing import Optional, List, Dict, Any, Tuple, Type, Callable
import time
import gc
import importlib
from pathlib import Path # Added import

from src.validator import validate_records # Only import generic now
from src.normalizer import ( # Will simplify imports later, but keep for now until specific calls are removed
    normalize_business_data,
    normalize_user_data,
    normalize_category_data,
    normalize_review_data,
    normalize_friend_data,
)
from src.loader import Neo4jLoader
from src.settings import settings, PhaseConfig # Import PhaseConfig

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


class PipelineRunner:
    def __init__(self, loader: Neo4jLoader, stats: PipelineStats):
        self.loader = loader
        self.stats = stats
        self.dead_letter_max_records_per_batch = settings.pipeline.dead_letter_max_records_per_batch
        self.models = self._load_models()

    def _load_models(self) -> Dict[str, Type]:
        """Dynamically load Pydantic models from src.models."""
        models_module = importlib.import_module("src.models")
        return {name: getattr(models_module, name) for name in models_module.__all__}

    def _get_callable(self, module_name: str, func_name: str) -> Callable:
        """Dynamically load a function from a module."""
        module = importlib.import_module(module_name)
        return getattr(module, func_name)

    def _load_generic_nodes(self, normalized_data: Dict[str, List[Dict[str, Any]]], phase_config: PhaseConfig, raw_records: List[Dict[str, Any]]) -> Tuple[int, int, List[Dict[str, Any]]]:
        """Loads nodes using the generic load_nodes method, and relationships if present."""
        total_nodes_created = 0
        total_rels_created = 0
        total_failed_records = []

        if normalized_data["nodes"]:
            nodes_created, failed = self.loader.load_nodes(
                normalized_data["nodes"], phase_config.node_label, phase_config.id_property
            )
            total_nodes_created += nodes_created
            total_failed_records.extend(failed)
        
        if normalized_data["relationships"]:
            rels_created, failed = self.loader.load_relationships(normalized_data["relationships"])
            total_rels_created += rels_created
            total_failed_records.extend(failed)

        return total_nodes_created, total_rels_created, total_failed_records

    def _load_relationships_only(self, normalized_data: Dict[str, List[Dict[str, Any]]], phase_config: PhaseConfig, raw_records: List[Dict[str, Any]]) -> Tuple[int, int, List[Dict[str, Any]]]:
        """Loads only relationships."""
        created_rels = 0
        failed_records = []
        if normalized_data["relationships"]:
            created_rels, failed_records = self.loader.load_relationships(normalized_data["relationships"])
        return 0, created_rels, failed_records

    def _load_nodes_and_relationships(self, normalized_data: Dict[str, List[Dict[str, Any]]], phase_config: PhaseConfig, raw_records: List[Dict[str, Any]]) -> Tuple[int, int, List[Dict[str, Any]]]:
        """Loads both nodes and relationships."""
        total_nodes_created = 0
        total_rels_created = 0
        total_failed_records = []

        # Load nodes first
        if normalized_data["nodes"]:
            nodes_created, failed = self.loader.load_nodes(
                normalized_data["nodes"], phase_config.node_label, phase_config.id_property
            )
            total_nodes_created += nodes_created
            total_failed_records.extend(failed)
        
        # Then load relationships
        if normalized_data["relationships"]:
            rels_created, failed = self.loader.load_relationships(normalized_data["relationships"])
            total_rels_created += rels_created
            total_failed_records.extend(failed)
            
        return total_nodes_created, total_rels_created, total_failed_records

    def _load_complex_business_data(self, normalized_data: Dict[str, List[Dict[str, Any]]], phase_config: PhaseConfig, raw_records: List[Dict[str, Any]]) -> Tuple[int, int, List[Dict[str, Any]]]:
        """
        Handles loading for the Business phase, which involves multiple node types
        and relationships from a single normalization pass.
        """
        total_nodes_created = 0
        total_rels_created = 0
        total_failed_records = []

        # The normalizer now returns distinct lists: business_nodes, postal_code_nodes, relationships
        business_nodes_to_load = normalized_data.get("business_nodes", [])
        postal_code_nodes_to_load = normalized_data.get("postal_code_nodes", [])
        relationships_to_load = normalized_data.get("relationships", [])

        # Load Business Nodes
        if business_nodes_to_load:
            created, failed = self.loader.load_nodes(
                business_nodes_to_load, "Business", "business_id"
            )
            total_nodes_created += created
            total_failed_records.extend(failed)

        # Load PostalCode Nodes (City and State are assumed pre-loaded)
        if postal_code_nodes_to_load:
            created, failed = self.loader.load_nodes(
                postal_code_nodes_to_load, "PostalCode", "code"
            )
            total_nodes_created += created
            total_failed_records.extend(failed)

        # Load all relationships
        if relationships_to_load:
            created, failed = self.loader.load_relationships(relationships_to_load)
            total_rels_created += created
            total_failed_records.extend(failed)
            
        return total_nodes_created, total_rels_created, total_failed_records

    def run_phase(self, phase_config: PhaseConfig, max_batches: Optional[int] = None):
        self.stats.log_phase_start(phase_config.name)
        logger.info(f"Loading {phase_config.name} (Phase {settings.pipeline.phases.index(phase_config) + 1} of {len(settings.pipeline.phases)})...")

        data_path = Path(settings.DATA_DIR) / phase_config.csv_file_name

        if not data_path.exists():
            logger.error(f"CSV not found for phase {phase_config.name}: {data_path}")
            return

        validator_func = self._get_callable("src.validator", phase_config.validator_func_name)
        normalizer_func = self._get_callable("src.normalizer", phase_config.normalizer_func_name)
        
        pydantic_model = self.models.get(phase_config.model_name)
        if pydantic_model is None:
            logger.error(f"Pydantic model '{phase_config.model_name}' not found for phase {phase_config.name}")
            return

        total_nodes_created_for_phase = 0
        total_rels_created_for_phase = 0

        batch_num = 0
        with pd.read_csv(data_path, chunksize=phase_config.chunk_size) as data_iter:
            for chunk in data_iter:
                batch_num += 1
                if max_batches and batch_num > max_batches:
                    break

                self.stats.total_rows_processed += len(chunk)
                raw_records = chunk.replace({float('nan'): None}).to_dict(orient="records")

                # Validate
                # validator_func now expects Pydantic model and entity name
                valid_records, invalid_records = validator_func(
                    raw_records, pydantic_model, phase_config.name, phase_config.id_property
                )
                self.stats.validation_failures += len(invalid_records)
                _write_dead_letters(invalid_records, self.dead_letter_max_records_per_batch) # Pass max_records

                if not valid_records:
                    logger.warning(f"Batch {batch_num} for {phase_config.name}: No valid records after validation")
                    # If no valid records, the loader strategy won't be called, so ensure counts are not updated.
                    # This batch is still processed in terms of rows, but doesn't create nodes/rels.
                    # This might increment failed_batches if raw_records exist but none are valid.
                    if len(raw_records) > 0: # If there were raw records but none were valid
                        self.stats.failed_batches += 1
                    continue

                # Normalize
                # normalizer_func now returns {"nodes": [...], "relationships": [...]}
                normalized_data = normalizer_func(valid_records) 

                # Load
                batch_nodes_created = 0
                batch_rels_created = 0
                failed_records_in_batch = [] # Track original raw records that failed to load

                _loader_dispatch = {
                    "load_nodes": self._load_generic_nodes,
                    "load_relationships": self._load_relationships_only,
                    "load_nodes_and_relationships": self._load_nodes_and_relationships,
                    "process_business_data": self._load_complex_business_data, # For the Business phase
                }

                loader_strategy = _loader_dispatch.get(phase_config.loader_method_name)

                if loader_strategy:
                    batch_nodes_created, batch_rels_created, batch_failed_records = loader_strategy(
                        normalized_data, phase_config, raw_records # Pass raw_records for dead-letter fallback
                    )
                    failed_records_in_batch.extend(batch_failed_records)
                else:
                    logger.error(f"Unknown loader method specified: {phase_config.loader_method_name} for phase {phase_config.name}")
                    failed_records_in_batch.extend(raw_records) # Mark all raw records as failed

                if failed_records_in_batch:
                    self.stats.failed_batches += 1
                    # Note: We are not counting individual failed records from loader here,
                    # but rather marking the whole batch as failed if any loader operation failed.
                    # The loader's dead letter mechanism handles individual records.
                else:
                    self.stats.successful_batches += 1
                    total_nodes_created_for_phase += batch_nodes_created
                    total_rels_created_for_phase += batch_rels_created
                    self.stats.total_nodes_created += batch_nodes_created
                    self.stats.total_rels_created += batch_rels_created


                logger.debug(f"Processed {batch_num * phase_config.chunk_size} records for {phase_config.name} so far")

        self.stats.log_phase_end(
            phase_config.name,
            nodes_created=total_nodes_created_for_phase,
            rels_created=total_rels_created_for_phase
        )


    def run_pipeline(self, max_batches: Optional[int] = None):
        """Orchestrates the entire ETL pipeline based on settings."""

        # Clear dead letter file
        os.makedirs(os.path.dirname(settings.DEAD_LETTER_FILE), exist_ok=True)
        with open(settings.DEAD_LETTER_FILE, "w") as f:
            f.write("")  # Clear file

        try:
            with self.loader:
                for phase_config in settings.pipeline.phases:
                    self.run_phase(phase_config, max_batches)

                logger.info("Performing final data integrity checks...")
                verify_data_integrity(self.loader)

                logger.info("Validating review counts...")
                validate_review_counts(self.loader, sample_size=1000)

        except Exception as e:
            logger.critical(f"FATAL: Pipeline failed with error: {e}", exc_info=True)
            raise

        finally:
            # Log final statistics
            summary = self.stats.get_summary()
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
                nodes = phase_data.get('nodes', 0)
                rels = phase_data.get('rels', 0)
                logger.info(f"  {phase}: {duration:.2f}s | Nodes: {nodes} | Rels: {rels}")

            # Write statistics to file
            stats_log_file = settings.LOG_FILE.parent / "pipeline_stats.json"
            with open(stats_log_file, "w") as f:
                json.dump(summary, f, indent=2)

            logger.info("ETL pipeline finished successfully")

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
            WHERE expected IS NOT NULL AND expected <> actual
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
    WHERE expected <> actual
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
    """Main ETL pipeline orchestrated by PipelineRunner."""
    logger.info("Starting Yelp ETL pipeline with optimal loading order (orchestrated by PipelineRunner)")

    stats = PipelineStats()
    try:
        loader = Neo4jLoader()
        runner = PipelineRunner(loader, stats)
        runner.run_pipeline(max_batches)
    except Exception as e:
        logger.critical(f"FATAL: Pipeline failed during initialization or execution: {e}", exc_info=True)
        raise

def _default_json_serializer(obj):
    """Helper to serialize non-JSON-serializable objects (like Exceptions, Paths, Pydantic models)."""
    from pydantic import BaseModel # Import locally to avoid circular dependencies at module level
    if isinstance(obj, (Path, Exception)):
        return str(obj)
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

def _standardize_error(error_item: Any) -> Dict[str, Any]:
    """Standardize a single error item into a serializable dictionary."""
    if isinstance(error_item, Exception):
        return {"type": type(error_item).__name__, "msg": str(error_item)}
    elif isinstance(error_item, dict):
        return error_item  # Assume Pydantic error dicts are already serializable
    else:
        return {"type": "unknown_error_format", "msg": str(error_item)}


def _write_dead_letters(records, max_records_per_batch: int = 500):
    """Write validation errors to dead letter queue with robust serialization."""
    if not records:
        return

    os.makedirs(os.path.dirname(settings.DEAD_LETTER_FILE), exist_ok=True) # Ensure directory exists

    with open(settings.DEAD_LETTER_FILE, "a", encoding="utf-8") as f:
        for r in records[:max_records_per_batch]:
            serializable_record = r.copy()

            # Standardize 'errors' field to be a list of serializable dicts
            if "errors" in serializable_record:
                errors_raw = serializable_record["errors"]
                processed_errors = []
                if not isinstance(errors_raw, list):
                    errors_raw = [errors_raw] # Ensure it's always iterable
                processed_errors = [_standardize_error(err_item) for err_item in errors_raw]
                serializable_record["errors"] = processed_errors
            
            # Truncate record data
            if "record" in serializable_record and isinstance(serializable_record["record"], dict):
                serializable_record["record"] = {
                    k: str(v)[:200] if not isinstance(v, (int, float, bool, type(None))) else v
                    for k, v in serializable_record["record"].items()
                }

            try:
                f.write(json.dumps(serializable_record, ensure_ascii=False, default=_default_json_serializer) + "\n")
            except Exception as e:
                logger.error(f"Failed to serialize record to dead letter: {serializable_record} - {e}", exc_info=True)
                f.write(json.dumps({"unserializable_record_fallback": str(serializable_record), "error": str(e)}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    run_pipeline()