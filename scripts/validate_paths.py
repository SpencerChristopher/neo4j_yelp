# scripts/validate_paths.py
import sys
from pathlib import Path

# Add the project root to the Python path to allow importing from 'src'
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.settings import settings
import logging

# Basic logging setup for the script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def validate_paths():
    """
    Performs a dry run to check if all CSV data files specified in the
    pipeline configuration exist on the filesystem.
    """
    logger.info("--- Starting Data Path Validation Dry Run ---")
    all_paths_valid = True
    
    # Get the configured data directory
    data_dir = settings.DATA_DIR
    logger.info(f"Using configured DATA_DIR: {data_dir.resolve()}")

    if not data_dir.exists():
        logger.error(f"[FATAL] The main data directory does not exist: {data_dir.resolve()}")
        return False

    # Iterate through each phase in the pipeline configuration
    for phase in settings.pipeline.phases:
        csv_path = data_dir / phase.csv_file_name

        logger.info(f"Checking for Phase '{phase.name}': {csv_path.resolve()}")

        if csv_path.exists():
            logger.info(f"[FOUND] ✅ File for phase '{phase.name}' exists.")
        else:
            logger.error(f"[MISSING] ❌ File for phase '{phase.name}' not found at {csv_path.resolve()}")
            all_paths_valid = False

    logger.info("--- Data Path Validation Dry Run Complete ---")
    return all_paths_valid

if __name__ == "__main__":
    if validate_paths():
        print("\n✅ All configured data paths are valid.")
        sys.exit(0)
    else:
        print("\n❌ One or more data paths are invalid. Please check the logs above.")
        sys.exit(1)
