# src/integrity_checks.py
import logging
from typing import Dict, Any, List

from src.loader import Neo4jLoader

logger = logging.getLogger(__name__)

def verify_data_integrity(loader: Neo4jLoader):
    """Perform comprehensive data integrity checks."""
    checks = [
        ("Total nodes", "MATCH (n) RETURN count(n) as total_nodes"),
        ("Total relationships", "MATCH ()-[r]-() RETURN count(r) as total_rels"),

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


def validate_review_counts(loader: Neo4jLoader, sample_size=100):
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
            logger.warning("✓ All business review counts match connected reviews")

        return len(mismatches)
