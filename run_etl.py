# run_etl.py
import argparse
import logging
import sys # Moved to top
from pathlib import Path
from src.pipeline import run_pipeline
from src.logging_config import setup_logging
from scripts.validate_paths import validate_paths # New import
from src.settings import settings

# It's good practice to set up logging at the entry point
setup_logging()
logger = logging.getLogger(__name__)

def main():
    """
    Main entry point for running the Yelp ETL pipeline for Neo4j.
    """
    parser = argparse.ArgumentParser(description="Run the Yelp data ETL pipeline for Neo4j.")
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="Limit the number of batches to process per phase. Useful for testing and debugging."
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="Data",
        help="Directory containing full data CSVs (default: Data)."
    )
    args = parser.parse_args()

    try:
        settings.DATA_DIR = Path(args.data_dir)
        # Perform path validation before starting the pipeline
        if not validate_paths():
            logger.critical("Data path validation failed. Aborting ETL pipeline.")
            sys.exit(1)

        logger.info("Starting ETL pipeline script...")
        run_pipeline(max_batches=args.max_batches)
        logger.info("ETL pipeline script finished successfully.")
    except Exception as e:
        logger.critical(f"ETL pipeline script failed with a fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
