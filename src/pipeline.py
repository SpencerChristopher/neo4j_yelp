import logging
import os
import json
import pandas as pd

from src.settings import (
    DATA_DIR,
    BUSINESS_CSV,
    BUSINESS_CITY_CSV,
    BATCH_SIZE,
    DEAD_LETTER_FILE, NEO4J_USER,
)

from src.validator import (
    validate_business_data,
    validate_canonical_city_state_data,
)

from src.normalizer import (
    normalize_business_data,
    normalize_canonical_city_state_data,
)

from src.loader import Neo4jLoader
from src.settings import (
    DATA_DIR,
    BUSINESS_CSV,
    BUSINESS_CITY_CSV,
    BATCH_SIZE,
    DEAD_LETTER_FILE,
    NEO4J_URI,
    NEO4J_ELT_USER,
    NEO4J_ELT_PASSWORD,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def run_pipeline():
    logger.info("Starting Yelp ETL pipeline")

    loader = Neo4jLoader(NEO4J_URI, NEO4J_USER, NEO4J_ELT_PASSWORD)
    try:
        # -------------------------
        # Dead letter setup
        # -------------------------
        os.makedirs(os.path.dirname(DEAD_LETTER_FILE), exist_ok=True)
        open(DEAD_LETTER_FILE, "w").close()


    # ==========================================================
    # PHASE 1 — Canonical City / State Skeleton
    # ==========================================================
    logger.info("PHASE 1: Loading canonical city/state skeleton")

    city_state_path = os.path.join(DATA_DIR, BUSINESS_CITY_CSV)
    city_state_iter = pd.read_csv(city_state_path, chunksize=BATCH_SIZE)

    for batch_num, chunk in enumerate(city_state_iter, start=1):
        logger.info(f"City/State batch {batch_num} ({len(chunk)} rows)")

        raw_records = chunk.fillna("").to_dict(orient="records")
        valid, invalid = validate_canonical_city_state_data(raw_records)

        _write_dead_letters(invalid)

        cities, states, rels = normalize_canonical_city_state_data(valid)

        loader.load_states(states)
        loader.load_cities(cities)
        loader.create_relationships(rels) # Assuming 'rels' is correctly formatted for create_relationships

    logger.info("PHASE 1 complete")

    # ==========================================================
    # PHASE 2 — Business Ingestion
    # ==========================================================
    logger.info("PHASE 2: Loading business data")

    business_path = os.path.join(DATA_DIR, BUSINESS_CSV)
    business_iter = pd.read_csv(business_path, chunksize=BATCH_SIZE)

    for batch_num, chunk in enumerate(business_iter, start=1):
        logger.info(f"Business batch {batch_num} ({len(chunk)} rows)")

        raw_records = chunk.fillna("").to_dict(orient="records")
        valid, invalid = validate_business_data(raw_records)

        _write_dead_letters(invalid)

        (
            business_nodes,
            city_claims,
            postal_claims,
        ) = normalize_business_data(valid)

        loader.load_businesses(business_nodes)
        loader.create_relationships(city_claims) # Assuming 'city_claims' are correctly formatted relationships
        loader.create_relationships(postal_claims) # Assuming 'postal_claims' are correctly formatted relationships

    logger.info("PHASE 2 complete")
    logger.info("ETL pipeline finished successfully")
    finally:
        loader.close()


def _write_dead_letters(records):
    if not records:
        return
    with open(DEAD_LETTER_FILE, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
