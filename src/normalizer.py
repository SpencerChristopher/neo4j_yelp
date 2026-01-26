from typing import List, Dict, Any, Tuple
from src.models.business import Business
from src.models.user import User
from src.models.review import Review
from src.models.category import Category
from src.models.friend import Friend
from src.models.city import City
from src.models.state import State
from src.models.postal_code import PostalCode
from pydantic import ValidationError
import logging

logger = logging.getLogger(__name__)


# ============================================================
# 1. BUSINESS NORMALIZATION
# ============================================================

def normalize_business_data(
        businesses: List[Business]
) -> Tuple[
    List[Dict[str, Any]],  # Business nodes
    List[Dict[str, Any]],  # State nodes
    List[Dict[str, Any]],  # City nodes
    List[Dict[str, Any]],  # PostalCode nodes
    List[Dict[str, Any]],  # Relationships (Business→City, Business→PostalCode, Business→State, City→State)
]:
    """
    Normalize Business models into Neo4j-ready payloads, extracting all geographic
    entities and relationships.
    """

    business_nodes: List[Dict[str, Any]] = []
    state_nodes_dict: Dict[str, State] = {}
    city_nodes_dict: Dict[str, City] = {}
    postal_code_nodes_dict: Dict[str, PostalCode] = {}

    relationships: List[Dict[str, Any]] = []

    for b in businesses:
        # Business node (with all direct properties) - ADDED review_count
        business_nodes.append({
            "business_id": b.business_id,
            "name": b.name,
            "stars": b.stars,
            "review_count": b.review_count,  # ADDED THIS LINE
            "is_open": b.is_open,
            "city": b.city,
            "state": b.state,
            "postal_code": b.postal_code,
            "latitude": b.location.latitude if b.location else None,
            "longitude": b.location.longitude if b.location else None,
        })

        # --- GEO ENTITY EXTRACTION ---
        # State Node
        if b.state:
            state_nodes_dict[b.state] = State(code=b.state)

        # PostalCode Node
        if b.postal_code:
            postal_code_nodes_dict[b.postal_code] = PostalCode(code=b.postal_code)

        # City Node
        if b.city and b.state:
            city_key = f"{b.city}|{b.state}"
            city_nodes_dict[city_key] = City(name=b.city, state_code=b.state)

        # --- RELATIONSHIP CREATION ---

        # Business -> State Relationship
        if b.state:
            relationships.append({
                "from_node_type": "Business", "from_node_id_prop": "business_id", "from_node_id_value": b.business_id,
                "to_node_type": "State", "to_node_id_prop": "code", "to_node_id_value": b.state,
                "relationship_type": "CLAIMS_STATE", "properties": {}
            })

        # Business -> PostalCode Relationship
        if b.postal_code:
            relationships.append({
                "from_node_type": "Business", "from_node_id_prop": "business_id", "from_node_id_value": b.business_id,
                "to_node_type": "PostalCode", "to_node_id_prop": "code", "to_node_id_value": b.postal_code,
                "relationship_type": "CLAIMS_POSTAL_CODE", "properties": {"source": "Yelp Data"}
            })

        # Business -> City Relationship
        if b.city and b.state:
            relationships.append({
                "from_node_type": "Business", "from_node_id_prop": "business_id", "from_node_id_value": b.business_id,
                "to_node_type": "City", "to_node_id_prop": "name", "to_node_id_value": b.city,
                "to_node_id_aux_prop": "state_code", "to_node_id_aux_value": b.state,
                "relationship_type": "LOCATED_NEAR", "properties": {
                    "latitude": b.location.latitude if b.location else None,
                    "longitude": b.location.longitude if b.location else None,
                }
            })

        # City -> State Relationship
        if b.city and b.state:
            relationships.append({
                "from_node_type": "City", "from_node_id_prop": "name", "from_node_id_value": b.city,
                "from_node_id_aux_prop": "state_code", "from_node_id_aux_value": b.state,
                "to_node_type": "State", "to_node_id_prop": "code", "to_node_id_value": b.state,
                "relationship_type": "CLAIMS_STATE", "properties": {}
            })

    # Deduplicate relationships (especially City->State which can be duplicated)
    def get_rel_key(rel):
        return (
            rel.get("relationship_type"),
            rel.get("from_node_type"),
            rel.get("from_node_id_value"),
            rel.get("from_node_id_aux_value", ""),
            rel.get("to_node_type"),
            rel.get("to_node_id_value"),
            rel.get("to_node_id_aux_value", "")
        )

    unique_relationships = {}
    for rel in relationships:
        key = get_rel_key(rel)
        unique_relationships[key] = rel

    relationships = list(unique_relationships.values())

    state_nodes = [s.model_dump() for s in state_nodes_dict.values()]
    city_nodes = [c.model_dump() for c in city_nodes_dict.values()]
    postal_code_nodes = [pc.model_dump() for pc in postal_code_nodes_dict.values()]

    logger.info(
        "Normalized %d businesses, %d states, %d cities, %d postal codes, and %d relationships",
        len(business_nodes), len(state_nodes), len(city_nodes), len(postal_code_nodes), len(relationships)
    )

    return business_nodes, state_nodes, city_nodes, postal_code_nodes, relationships


# ============================================================
# 2. USER NORMALIZATION
# ============================================================

def normalize_user_data(
        users: List[User]
) -> List[Dict[str, Any]]:
    """
    Normalize User models into Neo4j-ready node payloads.

    Returns flat structure matching User model fields.
    """

    user_nodes: List[Dict[str, Any]] = []

    for u in users:
        user_nodes.append(u.model_dump())

    logger.info("Normalized %d users", len(user_nodes))
    return user_nodes


# ============================================================
# 3. REVIEW NORMALIZATION
# ============================================================

def normalize_review_data(
        reviews: List[Review]
) -> Tuple[
    List[Dict[str, Any]],  # Review nodes
    List[Dict[str, Any]],  # WROTE relationships (User→Review)
    List[Dict[str, Any]],  # OF relationships (Review→Business)
]:
    """
    Normalize Review models into Neo4j-ready payloads.

    Critical for sentiment analysis - maintains review as evidence node.
    """

    review_nodes: List[Dict[str, Any]] = []
    wrote_relationships: List[Dict[str, Any]] = []
    of_relationships: List[Dict[str, Any]] = []

    for r in reviews:
        # Review node (evidence node with metadata)
        review_nodes.append(r.model_dump())

        # WROTE relationship (User→Review)
        wrote_relationships.append({
            "from_node_type": "User",
            "from_node_id_prop": "user_id",
            "from_node_id_value": r.user_id,
            "to_node_type": "Review",
            "to_node_id_prop": "review_id",
            "to_node_id_value": r.review_id,
            "relationship_type": "WROTE",
            "properties": {
                # Optional: Could add relationship properties here
                # "date": r.date,  # Already on Review node
            },
        })

        # OF relationship (Review→Business)
        of_relationships.append({
            "from_node_type": "Review",
            "from_node_id_prop": "review_id",
            "from_node_id_value": r.review_id,
            "to_node_type": "Business",
            "to_node_id_prop": "business_id",
            "to_node_id_value": r.business_id,
            "relationship_type": "OF",
            "properties": {},  # No additional properties needed
        })

    logger.info(
        "Normalized %d reviews | %d WROTE relationships | %d OF relationships",
        len(review_nodes), len(wrote_relationships), len(of_relationships)
    )

    return review_nodes, wrote_relationships, of_relationships


# ============================================================
# 4. CATEGORY NORMALIZATION
# ============================================================

def normalize_category_data(
        category_rows: List[Dict[str, Any]]  # Raw CSV rows: business_id, category
) -> Tuple[
    List[Dict[str, Any]],  # Category nodes (deduplicated)
    List[Dict[str, Any]],  # CLAIMS_CATEGORY relationships
]:
    """
    Normalize category data into canonical Category nodes and claims.

    Input: Raw rows from business_categories_small.csv
    Process: Deduplicate categories, create claim relationships
    """

    # Deduplicate categories by name
    category_nodes_dict: Dict[str, Dict[str, Any]] = {}
    category_relationships: List[Dict[str, Any]] = []

    for row in category_rows:
        business_id = row.get("business_id")
        category_name = row.get("category")

        if not business_id or not category_name:
            logger.warning(f"Skipping invalid category row: {row}")
            continue

        # Validate and clean category name using the Category model
        try:
            category_model = Category(name=category_name)
            cleaned_name = category_model.name
        except ValidationError as e:
            logger.warning(
                f"Skipping category '{category_name}' for business '{business_id}' due to validation error: {e}")
            continue

        # Add to deduplicated categories
        category_nodes_dict[cleaned_name] = {
            "name": cleaned_name,
        }

        # Create relationship specification
        category_relationships.append({
            "from_node_type": "Business",
            "from_node_id_prop": "business_id",
            "from_node_id_value": business_id,
            "to_node_type": "Category",
            "to_node_id_prop": "name",
            "to_node_id_value": cleaned_name,
            "relationship_type": "CLAIMS_CATEGORY",
            "properties": {
                "confidence": 1.0,  # Default confidence
                # Could compute confidence based on frequency or other factors
            },
        })

    category_nodes = list(category_nodes_dict.values())

    logger.info(
        "Normalized %d unique categories | %d category claims",
        len(category_nodes), len(category_relationships)
    )

    return category_nodes, category_relationships


# ============================================================
# 5. FRIEND NORMALIZATION - UPDATED: Removed since field
# ============================================================

def normalize_friend_data(
        friends: List[Friend]
) -> List[Dict[str, Any]]:
    """
    Normalize Friend models into FRIENDS_WITH relationships.

    Friend model already ensures:
    - No self-loops
    - Sorted user IDs (ensures undirected storage once)
    """

    friend_relationships: List[Dict[str, Any]] = []

    for f in friends:
        friend_relationships.append({
            "from_node_type": "User",
            "from_node_id_prop": "user_id",
            "from_node_id_value": f.user1,  # Already sorted by Friend model
            "to_node_type": "User",
            "to_node_id_prop": "user_id",
            "to_node_id_value": f.user2,
            "relationship_type": "FRIENDS_WITH",
            "properties": {},  # REMOVED: "since": f.since (CSV doesn't have this field)
        })

    logger.info("Normalized %d friend relationships", len(friend_relationships))
    return friend_relationships