from typing import List, Dict, Any, Tuple
from src.models.business import Business
from src.models.user import User
from src.models.review import Review
from src.models.category import Category, RawCategoryInput
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
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Normalize Business models into Neo4j-ready payloads, extracting relevant
    geographic relationships to pre-loaded canonical City/State nodes.
    Returns a dictionary with 'business_nodes', 'postal_code_nodes', and 'relationships' keys.
    """

    business_nodes: List[Dict[str, Any]] = []
    postal_code_nodes_dict: Dict[str, Dict[str, Any]] = {} # Store unique PostalCode dicts here
    all_relationships: List[Dict[str, Any]] = []

    for b in businesses:
        # Business node (with all direct properties)
        business_nodes.append({
            "business_id": b.business_id,
            "name": b.name,
            "stars": b.stars,
            "review_count": b.review_count,
            "is_open": b.is_open,
            "city": b.city,
            "state": b.state,
            "postal_code": b.postal_code,
            "latitude": b.location.latitude if b.location else None,
            "longitude": b.location.longitude if b.location else None,
        })

        # --- GEO ENTITY EXTRACTION (Only PostalCode here, as City/State are canonical) ---
        # PostalCode Node (for deduplication and later creation)
        if b.postal_code:
            postal_code_nodes_dict[b.postal_code] = PostalCode(code=b.postal_code).model_dump()


        # --- RELATIONSHIP CREATION ---

        # Business -> State Relationship (Links to pre-loaded State node)
        if b.state:
            normalized_state = State(code=b.state).code # Use Pydantic model for normalization
            all_relationships.append({
                "from_node_type": "Business", "from_node_id_prop": "business_id", "from_node_id_value": b.business_id,
                "to_node_type": "State", "to_node_id_prop": "code", "to_node_id_value": normalized_state,
                "relationship_type": "CLAIMS_STATE", "properties": {},
                "from_node_properties": {}, "to_node_properties": {} # Add empty props for loader
            })

        # Business -> PostalCode Relationship
        if b.postal_code:
            all_relationships.append({
                "from_node_type": "Business", "from_node_id_prop": "business_id", "from_node_id_value": b.business_id,
                "to_node_type": "PostalCode", "to_node_id_prop": "code", "to_node_id_value": b.postal_code,
                "relationship_type": "CLAIMS_POSTAL_CODE", "properties": {"source": "Yelp Data"},
                "from_node_properties": {}, "to_node_properties": {} # Add empty props for loader
            })

        # Business -> City Relationship (Links to pre-loaded City node)
        if b.city and b.state:
            normalized_city_model = City(name=b.city, state_code=b.state) # Use Pydantic model for normalization
            all_relationships.append({
                "from_node_type": "Business", "from_node_id_prop": "business_id", "from_node_id_value": b.business_id,
                "to_node_type": "City", "to_node_id_prop": "name", "to_node_id_value": normalized_city_model.name,
                "to_node_id_aux_prop": "state_code", "to_node_id_aux_value": normalized_city_model.state_code,
                "relationship_type": "LOCATED_NEAR",
                "properties": {
                    "latitude": b.location.latitude if b.location else None,
                    "longitude": b.location.longitude if b.location else None,
                },
                "from_node_properties": {}, "to_node_properties": {} # Add empty props for loader
            })

    # Deduplicate relationships (logic remains the same)
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
    for rel in all_relationships:
        key = get_rel_key(rel)
        unique_relationships[key] = rel

    all_relationships = list(unique_relationships.values())

    logger.info(
        "Normalized %d business nodes, %d postal code nodes, and %d relationships",
        len(business_nodes), len(postal_code_nodes_dict), len(all_relationships)
    )

    return {
        "business_nodes": business_nodes,
        "postal_code_nodes": list(postal_code_nodes_dict.values()),
        "relationships": all_relationships
    }

# ============================================================
# 2. USER NORMALIZATION
# ============================================================

def normalize_user_data(
        users: List[User]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Normalize User models into Neo4j-ready node payloads.
    Returns a dictionary with 'nodes' and 'relationships' keys.
    """

    user_nodes: List[Dict[str, Any]] = []

    for u in users:
        user_nodes.append(u.model_dump())

    logger.info("Normalized %d users", len(user_nodes))
    return {"nodes": user_nodes, "relationships": []}


# ============================================================
# 3. REVIEW NORMALIZATION
# ============================================================

def normalize_review_data(
        reviews: List[Review]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Normalize Review models into Neo4j-ready payloads.
    Returns a dictionary with 'nodes' and 'relationships' keys.

    Critical for sentiment analysis - maintains review as evidence node.
    """

    review_nodes: List[Dict[str, Any]] = []
    all_relationships: List[Dict[str, Any]] = []

    for r in reviews:
        # Review node (evidence node with metadata)
        review_nodes.append(r.model_dump())

        # WROTE relationship (User→Review)
        all_relationships.append({
            "from_node_type": "User",
            "from_node_id_prop": "user_id",
            "from_node_id_value": r.user_id,
            "to_node_type": "Review",
            "to_node_id_prop": "review_id",
            "to_node_id_value": r.review_id,
            "relationship_type": "WROTE",
            "properties": {},
            "from_node_properties": {}, "to_node_properties": {} # Add empty props for loader
        })

        # OF relationship (Review→Business)
        all_relationships.append({
            "from_node_type": "Review",
            "from_node_id_prop": "review_id",
            "from_node_id_value": r.review_id,
            "to_node_type": "Business",
            "to_node_id_prop": "business_id",
            "to_node_id_value": r.business_id,
            "relationship_type": "OF",
            "properties": {},
            "from_node_properties": {}, "to_node_properties": {} # Add empty props for loader
        })

    logger.info(
        "Normalized %d reviews | %d relationships",
        len(review_nodes), len(all_relationships)
    )

    return {"nodes": review_nodes, "relationships": all_relationships}


# ============================================================
# 4. CATEGORY NORMALIZATION
# ============================================================

def normalize_category_data(
        category_rows: List[RawCategoryInput]  # Now expects validated RawCategoryInput
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Normalize validated RawCategoryInput models into canonical Category nodes and claims.
    Returns a dictionary with 'nodes' and 'relationships' keys.

    Input: List of validated RawCategoryInput instances.
    Process: Deduplicate categories, create claim relationships.
    """

    category_nodes_dict: Dict[str, Dict[str, Any]] = {}
    category_relationships: List[Dict[str, Any]] = []

    for row in category_rows:
        business_id = row.business_id
        # The category name is already cleaned and validated by RawCategoryInput
        cleaned_name = row.category

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
            },
            "from_node_properties": {}, "to_node_properties": {} # Add empty props for loader
        })

    category_nodes = list(category_nodes_dict.values())

    logger.info(
        "Normalized %d unique categories | %d category claims",
        len(category_nodes), len(category_relationships)
    )

    return {"nodes": category_nodes, "relationships": category_relationships}


# ============================================================
# 5. FRIEND NORMALIZATION - UPDATED: Removed since field
# ============================================================

def normalize_friend_data(
        friends: List[Friend]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Normalize Friend models into FRIENDS_WITH relationships.
    Returns a dictionary with 'nodes' and 'relationships' keys.

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
            "properties": {},
            "from_node_properties": {}, "to_node_properties": {} # Add empty props for loader
        })

    logger.info("Normalized %d friend relationships", len(friend_relationships))
    return {"nodes": [], "relationships": friend_relationships}


# ============================================================
# 6. CANONICAL CITY/STATE NORMALIZATION
# ============================================================

def normalize_canonical_city_state_data(
        city_models: List[City] # Expects validated Pydantic City models
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Normalize validated City models into canonical City nodes and their
    corresponding CLAIMS_STATE relationships. State nodes are created or merged
    by the loader during relationship creation.
    """
    city_nodes: List[Dict[str, Any]] = []
    all_relationships: List[Dict[str, Any]] = []

    # Use dicts for deduplication before creating the final lists
    unique_cities: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for city_model in city_models:
        try:
            # Deduplicate city nodes
            city_key = (city_model.name, city_model.state_code)
            if city_key not in unique_cities:
                unique_cities[city_key] = city_model.model_dump()

            # Create IN relationship from City to State
            all_relationships.append({
                "from_node_type": "City",
                "from_node_id_prop": "name",
                "from_node_id_value": city_model.name,
                "from_node_id_aux_prop": "state_code",
                "from_node_id_aux_value": city_model.state_code,
                "to_node_type": "State",
                "to_node_id_prop": "code",
                "to_node_id_value": city_model.state_code, # state_code from City model is the State's code
                "relationship_type": "IN",
                "properties": {},
                "from_node_properties": {}, "to_node_properties": {}
            })

        except Exception as e:
            logger.error(f"Error processing canonical city/state record: {city_model} - {e}")

    city_nodes = list(unique_cities.values())

    logger.info(
        "Normalized %d unique canonical cities | %d relationships to states",
        len(city_nodes), len(all_relationships)
    )

    return {"nodes": city_nodes, "relationships": all_relationships}
