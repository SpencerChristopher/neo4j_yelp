from typing import List, Dict, Any, Tuple
from src.models.business import Business
from src.models.user import User
import logging

logger = logging.getLogger(__name__)


# ============================================================
# Phase 2 — Business normalization (claims only)
# ============================================================

def normalize_business_data(
    businesses: List[Business]
) -> Tuple[
    List[Dict[str, Any]],  # Business nodes
    List[Dict[str, Any]],  # Business → City claims
    List[Dict[str, Any]],  # Business → PostalCode claims
]:
    """
    Normalize validated Business models into Neo4j-ready node and relationship payloads.

    IMPORTANT:
    - Does NOT create City, State, or PostalCode nodes
    - Does NOT create City→State relationships
    - Emits only Business nodes and their claims
    """

    business_nodes: List[Dict[str, Any]] = []
    city_claims: List[Dict[str, Any]] = []
    postal_claims: List[Dict[str, Any]] = []

    for b in businesses:
        # -------------------------
        # Business node
        # -------------------------
        business_nodes.append({
            "business_id": b.business_id,
            "name": b.name,
            "stars": b.stars,
            "is_open": b.is_open,
        })

        # -------------------------
        # City claim (soft location)
        # -------------------------
        if b.city:
            city_claims.append({
                "business_id": b.business_id,
                "city": b.city,
                "state": b.state,
                "latitude": b.location.latitude if b.location else None,
                "longitude": b.location.longitude if b.location else None,
            })

        # -------------------------
        # Postal code claim (stronger signal)
        # -------------------------
        if b.postal_code:
            postal_claims.append({
                "business_id": b.business_id,
                "postal_code": b.postal_code,
            })

    logger.info(
        "Normalized %d businesses | %d city claims | %d postal claims",
        len(business_nodes),
        len(city_claims),
        len(postal_claims),
    )

    return business_nodes, city_claims, postal_claims


# ============================================================
# Phase 1 — Canonical City / State normalization
# ============================================================

def normalize_canonical_city_state_data(
    canonical_city_states
) -> Tuple[
    List[Dict[str, Any]],  # City nodes
    List[Dict[str, Any]],  # State nodes
    List[Dict[str, Any]],  # City → State relationships
]:
    """
    Normalize canonical city/state rows into unique nodes and relationships.

    This function is Phase-1 ONLY.
    """

    cities = {}
    states = {}
    relationships = []

    for row in canonical_city_states:
        state_code = row.state_code
        city_name = row.city

        states[state_code] = {"code": state_code}

        city_key = f"{city_name}|{state_code}"
        cities[city_key] = {
            "name": city_name,
            "state": state_code,
        }

        relationships.append({
            "city": city_name,
            "state": state_code,
        })

    logger.info(
        "Canonical normalization: %d cities | %d states | %d relationships",
        len(cities),
        len(states),
        len(relationships),
    )

    return (
        list(cities.values()),
        list(states.values()),
        relationships,
    )



def normalize_user_data(
    users: list[User]
) -> list[dict]:

    normalized = []

    for u in users:
        normalized.append({
            "user_id": u.user_id,
            "name": u.name,
            "review_count": u.review_count,
            "yelping_since": u.yelping_since,
            "fans": u.fans,
            "average_stars": u.average_stars,
            "compliments": {
                "hot": u.compliment_hot,
                "more": u.compliment_more,
                "profile": u.compliment_profile,
                "cute": u.compliment_cute,
                "list": u.compliment_list,
                "note": u.compliment_note,
                "plain": u.compliment_plain,
                "cool": u.compliment_cool,
                "funny": u.compliment_funny,
                "writer": u.compliment_writer,
                "photos": u.compliment_photos,
            }
        })

    return normalized
