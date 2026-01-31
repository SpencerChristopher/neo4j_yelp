from typing import List, Dict, Any, Tuple, Type, Callable
from pydantic import ValidationError, BaseModel
import logging

from src.models.business import Business
from src.models.user import User
from src.models.review import Review
from src.models.category import Category, RawCategoryInput
from src.models.friend import Friend
from src.models.city import City # Import City model

logger = logging.getLogger(__name__)


def _create_error_record(
        row_number: int,
        entity: str,
        record: Dict[str, Any],
        errors: List[Dict[str, Any]],
        **additional_fields
) -> Dict[str, Any]:
    """
    Create consistent error record format for dead letter queue.

    Args:
        row_number: CSV row number (1-indexed)
        entity: Entity type ("Business", "User", etc.)
        record: Original raw record
        errors: List of Pydantic error dicts
        additional_fields: Entity-specific fields (business_id, user_id, etc.)
    """
    error_record = {
        "row_number": row_number,
        "entity": entity,
        "record": record,
        "errors": errors,
    }
    error_record.update(additional_fields)
    return error_record


def validate_records(
    raw_records: List[Dict[str, Any]],
    pydantic_model: Type[BaseModel],
    entity_name: str,
    identifier_field: str = None # Field to use for logging/dead-letter identification
) -> Tuple[List[BaseModel], List[Dict[str, Any]]]:
    valid_records: List[BaseModel] = []
    invalid_records: List[Dict[str, Any]] = []

    for idx, record in enumerate(raw_records, start=1):
        try:
            validated_instance = pydantic_model(**record)
            valid_records.append(validated_instance)

        except ValidationError as e:
            additional_fields = {}
            if identifier_field and identifier_field in record:
                additional_fields[identifier_field] = record.get(identifier_field)

            invalid_records.append(_create_error_record(
                row_number=idx,
                entity=entity_name,
                record=record,
                errors=e.errors(),
                **additional_fields
            ))
            logger.warning(
                "%s validation failed | row=%d | %s=%s | errors=%d",
                entity_name, idx,
                identifier_field if identifier_field else "N/A",
                record.get(identifier_field, "N/A") if identifier_field else "N/A",
                len(e.errors())
            )

        except Exception as e:
            additional_fields = {}
            if identifier_field and identifier_field in record:
                additional_fields[identifier_field] = record.get(identifier_field)

            invalid_records.append(_create_error_record(
                row_number=idx,
                entity=entity_name,
                record=record,
                errors=[{"type": "unexpected", "msg": str(e)}],
                **additional_fields
            ))
            logger.error(
                "Unexpected %s validation error | row=%d | %s=%s",
                entity_name, idx,
                identifier_field if identifier_field else "N/A",
                record.get(identifier_field, "N/A") if identifier_field else "N/A",
                exc_info=True
            )

    logger.warning(
        "%s validation: %d valid, %d invalid",
        entity_name, len(valid_records), len(invalid_records)
    )

    return valid_records, invalid_records


# ============================================================
# BUSINESS VALIDATION
# ============================================================

def validate_business_data(
        raw_records: List[Dict[str, Any]],
        pydantic_model: Type[BaseModel],
        entity_name: str,
        identifier_field: str
) -> Tuple[List[Business], List[Dict[str, Any]]]:
    # The incoming arguments (pydantic_model, etc.) are ignored in favor of the hardcoded ones.
    return validate_records(raw_records, Business, "Business", identifier_field="business_id")


# ============================================================
# USER VALIDATION
# ============================================================

def validate_user_data(
        raw_records: List[Dict[str, Any]],
        pydantic_model: Type[BaseModel],
        entity_name: str,
        identifier_field: str
) -> Tuple[List[User], List[Dict[str, Any]]]:
    return validate_records(raw_records, User, "User", identifier_field="user_id")


# ============================================================
# REVIEW VALIDATION
# ============================================================

def validate_review_data(
        raw_records: List[Dict[str, Any]],
        pydantic_model: Type[BaseModel],
        entity_name: str,
        identifier_field: str
) -> Tuple[List[Review], List[Dict[str, Any]]]:
    # Review has multiple identifiers, so use review_id for logging
    return validate_records(raw_records, Review, "Review", identifier_field="review_id")


# ============================================================
# CATEGORY VALIDATION (Raw CSV rows)
# ============================================================

def validate_category_data(
        raw_records: List[Dict[str, Any]],
        pydantic_model: Type[BaseModel],
        entity_name: str,
        identifier_field: str
) -> Tuple[List[RawCategoryInput], List[Dict[str, Any]]]:
    """
    Validates raw category rows (business_id, category) using RawCategoryInput model.
    Returns validated RawCategoryInput instances and invalid records.
    """
    return validate_records(raw_records, RawCategoryInput, "RawCategoryInput", identifier_field="business_id")





# ============================================================
# CITY VALIDATION (Canonical city/state)
# ============================================================

from src.models.city import City # Import City model

def validate_city_state_data(
        raw_records: List[Dict[str, Any]],
        pydantic_model: Type[BaseModel],
        entity_name: str,
        identifier_field: str
) -> Tuple[List[City], List[Dict[str, Any]]]:
    """
    Validates raw city/state records using the City Pydantic model.
    This function also pre-processes the records to align CSV headers ('city', 'state')
    with the Pydantic model's field names ('name', 'state_code').
    """
    processed_records = []
    for record in raw_records:
        processed_record = {
            'name': record.get('city'),
            'state_code': record.get('state')
        }
        processed_records.append(processed_record)

    # Use 'city' as the identifier field for logging dead letters.
    # The 'state' field in the raw record will be mapped to 'state_code' in the City model.
    # The City model's validation will handle state_code constraints.
    return validate_records(processed_records, pydantic_model, entity_name, identifier_field)


# ============================================================
# BULK VALIDATION (Optional helper)
# ============================================================

def validate_all_entities(
        business_records: List[Dict[str, Any]] = None,
        user_records: List[Dict[str, Any]] = None,
        review_records: List[Dict[str, Any]] = None,
        category_records: List[Dict[str, Any]] = None,
        friend_records: List[Dict[str, Any]] = None,
) -> Dict[str, Tuple[List[Any], List[Dict[str, Any]]]]:
    """
    Validate multiple entity types in one call.

    Returns dict with keys: business, user, review, category, friend
    Each value is tuple of (valid_records, invalid_records)
    """
    results = {}

    if business_records is not None:
        results["business"] = validate_business_data(business_records)

    if user_records is not None:
        results["user"] = validate_user_data(user_records)

    if review_records is not None:
        results["review"] = validate_review_data(review_records)

    if category_records is not None:
        results["category"] = validate_category_data(category_records)

    if friend_records is not None:
        results["friend"] = validate_friend_data(friend_records)

    # Log summary
    total_valid = sum(len(v[0]) for v in results.values())
    total_invalid = sum(len(v[1]) for v in results.values())
    logger.info(
        "Bulk validation complete: %d total valid, %d total invalid across %d entity types",
        total_valid, total_invalid, len(results)
    )

    return results