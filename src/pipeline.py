import logging
import os
import json
import pandas as pd
from typing import Optional, List, Dict, Any, Tuple, Type, Callable
import time
import gc
import importlib
from pathlib import Path

from src.loader import Neo4jLoader
from neo4j.exceptions import ClientError
from src.settings import settings, PhaseConfig
from src.integrity_checks import verify_data_integrity, validate_review_counts
from src.dead_letter_handler import write_dead_letters

from src.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class PipelineConfigError(Exception):
    """Custom exception for pipeline configuration errors."""
    pass


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
        logger.warning(f"=== STARTING PHASE: {phase_name} ===")

    def log_phase_end(self, phase_name, nodes_created=0, rels_created=0):
        if phase_name in self.phase_stats:
            duration = time.time() - self.phase_stats[phase_name]["start"]
            self.phase_stats[phase_name]["duration"] = duration
            self.phase_stats[phase_name]["nodes"] = nodes_created
            self.phase_stats[phase_name]["rels"] = rels_created
            logger.warning(f"=== COMPLETED PHASE: {phase_name} in {duration:.2f}s ===")

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

        self._loader_dispatch = {
            "load_nodes": self._load_nodes_and_rels_generic,
            "load_relationships": self._load_relationships_only,
            "load_nodes_and_relationships": self._load_nodes_and_rels_generic,
            "process_business_data": self._load_complex_business_data,
            "load_friends_apoc": self._load_friends_apoc_data,
            "none": lambda nd, pc, rr: (0, 0, [])
        }

    def _load_models(self) -> Dict[str, Type]:
        """Dynamically load Pydantic models from src.models."""
        models_module = importlib.import_module("src.models")
        return {name: getattr(models_module, name) for name in models_module.__all__}

    def _get_callable(self, module_name: str, func_name: str) -> Callable:
        """Dynamically load a function from a module."""
        module = importlib.import_module(module_name)
        return getattr(module, func_name)



    def _load_relationships_only(self, normalized_data: Dict[str, List[Dict[str, Any]]], phase_config: PhaseConfig, raw_records: List[Dict[str, Any]]) -> Tuple[int, int, List[Dict[str, Any]]]:
        """Loads only relationships."""
        created_rels = 0
        failed_records = []
        if normalized_data["relationships"]:
            created_rels, failed_records = self.loader.load_relationships(normalized_data["relationships"])
        return 0, created_rels, failed_records

    def _load_nodes_and_rels_generic(self, normalized_data: Dict[str, List[Dict[str, Any]]], phase_config: PhaseConfig, raw_records: List[Dict[str, Any]]) -> Tuple[int, int, List[Dict[str, Any]]]:
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

    def _load_friends_apoc_data(self, normalized_data: Dict[str, Any], phase_config: PhaseConfig, raw_records: List[Dict[str, Any]]) -> Tuple[int, int, List[Dict[str, Any]]]:
        """
        Handles loading friend relationships using server-side APOC.
        Client-side validation and normalization are bypassed for this method.
        """
        created_nodes = 0 # APOC only creates relationships, not nodes directly in this context
        created_rels = 0
        failed_records: List[Dict[str, Any]] = []

        try:
            batches_processed, rels_created, errors = self.loader.load_friend_relationships_apoc(
                str(phase_config.csv_file_name)
            )
            created_rels += rels_created
            # For APOC, we consider errors reported by APOC itself, not individual records
            if errors:
                failed_records.append({"error_type": "APOC_ERROR", "message": errors})

        except Exception as e:
            logger.error(f"Failed server-side APOC loading for {phase_config.name}: {e}", exc_info=True)
            failed_records.append({"error_type": "EXCEPTION", "message": str(e)})

        return created_nodes, created_rels, failed_records

    def run_phase(self, phase_config: PhaseConfig, max_batches: Optional[int] = None):
        """
        Executes a single phase of the ETL pipeline.

        This method orchestrates data loading for a specific phase, handling:
        - Reading data from the specified CSV.
        - Validation using a dynamically loaded Pydantic model and validator function.
        - Normalization using a dynamically loaded normalizer function.
        - Loading into Neo4j using a specified loader method.

        Args:
            phase_config: Configuration for the current phase (PhaseConfig object).
            max_batches: Optional maximum number of batches to process for this phase.
        """
        self.stats.log_phase_start(phase_config.name)
        logger.warning(f"Loading {phase_config.name} (Phase {settings.pipeline.phases.index(phase_config) + 1} of {len(settings.pipeline.phases)})...")

        total_nodes_created_for_phase = 0
        total_rels_created_for_phase = 0
        
        try:
            data_path = Path(settings.DATA_DIR) / phase_config.csv_file_name

            if not data_path.exists():
                logger.error(f"CSV not found for phase {phase_config.name}: {data_path}")
                # Early exit, finally block will still be called to log phase end
                return

            pydantic_model = self.models.get(phase_config.model_name)
            if pydantic_model is None and phase_config.loader_method_name != "load_friends_apoc":
                logger.error(f"Pydantic model '{phase_config.model_name}' not found for phase {phase_config.name}")
                return # Early exit, finally block will still be called

            # Determine if client-side validation/normalization is needed
            perform_client_side_processing = phase_config.loader_method_name not in ["load_friends_apoc", "none"]

            validator_func = None
            normalizer_func = None
            if perform_client_side_processing:
                validator_func = self._get_callable("src.validator", phase_config.validator_func_name)
                normalizer_func = self._get_callable("src.normalizer", phase_config.normalizer_func_name)
            
            batch_num = 0
            with pd.read_csv(data_path, chunksize=phase_config.chunk_size) as data_iter:
                for chunk in data_iter:
                    batch_num += 1
                    if max_batches and batch_num > max_batches:
                        break

                    self.stats.total_rows_processed += len(chunk)
                    raw_records = chunk.replace({float('nan'): None}).to_dict(orient="records")

                    valid_records = []
                    invalid_records = []
                    normalized_data = {}

                    if perform_client_side_processing:
                        # Validate
                        valid_records, invalid_records = validator_func(
                            raw_records, pydantic_model, phase_config.name, phase_config.id_property
                        )
                        self.stats.validation_failures += len(invalid_records)
                        write_dead_letters(invalid_records, self.dead_letter_max_records_per_batch)

                        if not valid_records:
                            logger.warning(f"Batch {batch_num} for {phase_config.name}: No valid records after validation")
                            if len(raw_records) > 0:
                                self.stats.failed_batches += 1
                            continue
                        
                        # Normalize
                        # normalizer_func is dynamically loaded above
                        normalized_data = normalizer_func(valid_records) 
                    elif phase_config.loader_method_name == "load_friends_apoc":
                        # For APOC, no client-side validation/normalization needed,
                        # but pass raw_records if needed by the loader strategy for context
                        normalized_data = {"raw_records": raw_records} 
                    else:
                        # For "none" loader method, just pass raw records (e.g., for direct loader calls in tests)
                        normalized_data = {"raw_records": raw_records}
                    
                    # Load
                    batch_nodes_created = 0
                    batch_rels_created = 0
                    failed_records = []

                    loader_strategy = self._loader_dispatch.get(phase_config.loader_method_name)

                    if loader_strategy:
                        # Pass normalized_data (which might contain valid_records or raw_records)
                        # and raw_records (for dead-letter fallback)
                        batch_nodes_created, batch_rels_created, batch_failed_records = loader_strategy(
                            normalized_data, phase_config, raw_records
                        )
                        failed_records.extend(batch_failed_records)
                    else:
                        logger.error(f"Unknown loader method specified: {phase_config.loader_method_name} for phase {phase_config.name}")
                        failed_records.extend(raw_records)

                    if failed_records:
                        self.stats.failed_batches += 1
                        self.stats.batch_failures += 1
                    else:
                        self.stats.successful_batches += 1
                        total_nodes_created_for_phase += batch_nodes_created
                        total_rels_created_for_phase += batch_rels_created
                        self.stats.total_nodes_created += batch_nodes_created
                        self.stats.total_rels_created += batch_rels_created

                    logger.debug(f"Processed {batch_num * phase_config.chunk_size} records for {phase_config.name} so far")

        finally:
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

                logger.warning("Performing final data integrity checks...")
                verify_data_integrity(self.loader)

                logger.warning("Validating review counts...")
                validate_review_counts(self.loader, sample_size=1000)

        except Exception as e:
            logger.critical(f"FATAL: Pipeline failed with error: {e}", exc_info=True)
            raise

        finally:
            # Log final statistics
            summary = self.stats.get_summary()
            logger.warning(f"""
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
                logger.warning(f"  {phase}: {duration:.2f}s | Nodes: {nodes} | Rels: {rels}")

            # Write statistics to file
            stats_log_file = settings.LOG_FILE.parent / "pipeline_stats.json"
            with open(stats_log_file, "w") as f:
                json.dump(summary, f, indent=2)

            logger.warning("ETL pipeline finished successfully")




def run_pipeline(max_batches: Optional[int] = None):
    """Main ETL pipeline orchestrated by PipelineRunner."""
    logger.warning("Starting Yelp ETL pipeline with optimal loading order (orchestrated by PipelineRunner)")

    stats = PipelineStats()
    try:
        loader = Neo4jLoader()
        runner = PipelineRunner(loader, stats)
        runner.run_pipeline(max_batches)
    except Exception as e:
        logger.critical(f"FATAL: Pipeline failed during initialization or execution: {e}", exc_info=True)
        raise




if __name__ == "__main__":
    run_pipeline()
