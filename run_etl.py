# run_etl.py
import argparse
import logging
from src.pipeline import run_pipeline
from src.logging_config import setup_logging

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
    args = parser.parse_args()

    try:
        logger.info("Starting ETL pipeline script...")
        run_pipeline(max_batches=args.max_batches)
        logger.info("ETL pipeline script finished successfully.")
    except Exception as e:
        logger.critical(f"ETL pipeline script failed with a fatal error: {e}", exc_info=True)
        # In a production script, you might exit with a non-zero status code
        import sys
        sys.exit(1)

if __name__ == "__main__":
    main()
