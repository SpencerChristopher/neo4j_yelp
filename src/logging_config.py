import logging
import logging.handlers
import os


def setup_logging():
    """Configure logging with separate files and memory-safe settings."""

    # Create logs directory
    os.makedirs("logs", exist_ok=True)

    # Clear handlers
    logging.root.handlers = []

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)

    # CRITICAL ERRORS ONLY - loader_critical.log (10MB max, 5 backups)
    critical_handler = logging.handlers.RotatingFileHandler(
        "logs/loader_critical.log",
        maxBytes=10_000_000,
        backupCount=5,
        delay=True
    )
    critical_handler.setLevel(logging.ERROR)
    critical_handler.addFilter(lambda record: "loader" in record.name.lower())

    # VALIDATOR ERRORS - validator_errors.log (5MB max, 3 backups)
    validator_handler = logging.handlers.RotatingFileHandler(
        "logs/validator_errors.log",
        maxBytes=5_000_000,
        backupCount=3,
        delay=True
    )
    validator_handler.setLevel(logging.WARNING)
    validator_handler.addFilter(lambda record: "validator" in record.name.lower())

    # GENERAL PIPELINE LOG - pipeline.log (50MB max, 10 backups)
    pipeline_handler = logging.handlers.RotatingFileHandler(
        "logs/pipeline.log",
        maxBytes=50_000_000,
        backupCount=10,
        delay=True
    )
    pipeline_handler.setLevel(logging.INFO)

    # CONSOLE for debugging
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Formatter - simple format to save space
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    for handler in [critical_handler, validator_handler, pipeline_handler, console_handler]:
        handler.setFormatter(formatter)

    # Assign handlers
    root_logger.addHandler(critical_handler)
    root_logger.addHandler(validator_handler)
    root_logger.addHandler(pipeline_handler)
    root_logger.addHandler(console_handler)

    # Set specific loggers to higher levels to avoid noise
    logging.getLogger("neo4j").setLevel(logging.WARNING)
    logging.getLogger("tenacity").setLevel(logging.WARNING)

    return root_logger