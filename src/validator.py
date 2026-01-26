from typing import List, Dict, Any, Tuple
from pydantic import ValidationError
from src.models.business import Business
from src.models.user import User
from src.models.review import Review
from src.models.category import Category
from src.models.friend import Friend
import logging

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


# ============================================================
# BUSINESS VALIDATION
# ============================================================

def validate_business_data(
        raw_records: List[Dict[str, Any]]
) -> Tuple[List[Business], List[Dict[str, Any]]]:
    valid_records: List[Business] = []
    invalid_records: List[Dict[str, Any]] = []

    for idx, record in enumerate(raw_records, start=1):
        try:
            valid_records.append(Business(**record))

        except ValidationError as e:
            invalid_records.append(_create_error_record(
                row_number=idx,
                entity="Business",
                record=record,
                errors=e.errors(),
                business_id=record.get("business_id"),
            ))
            logger.warning(
                "Business validation failed | row=%d | business_id=%s | errors=%d",
                idx, record.get("business_id", "N/A"), len(e.errors())
            )

        except Exception as e:
            invalid_records.append(_create_error_record(
                row_number=idx,
                entity="Business",
                record=record,
                errors=[{"type": "unexpected", "msg": str(e)}],
                business_id=record.get("business_id"),
            ))
            logger.error(
                "Unexpected business validation error | row=%d | business_id=%s",
                idx, record.get("business_id", "N/A"),
                exc_info=True
            )

    logger.info(
        "Business validation: %d valid, %d invalid",
        len(valid_records), len(invalid_records)
    )

    return valid_records, invalid_records


# ============================================================
# USER VALIDATION
# ============================================================

def validate_user_data(
        raw_records: List[Dict[str, Any]]
) -> Tuple[List[User], List[Dict[str, Any]]]:
    valid_records: List[User] = []
    invalid_records: List[Dict[str, Any]] = []

    for idx, record in enumerate(raw_records, start=1):
        try:
            valid_records.append(User(**record))

        except ValidationError as e:
            invalid_records.append(_create_error_record(
                row_number=idx,
                entity="User",
                record=record,
                errors=e.errors(),
                user_id=record.get("user_id"),
            ))
            logger.warning(
                "User validation failed | row=%d | user_id=%s | errors=%d",
                idx, record.get("user_id", "N/A"), len(e.errors())
            )

        except Exception as e:
            invalid_records.append(_create_error_record(
                row_number=idx,
                entity="User",
                record=record,
                errors=[{"type": "unexpected", "msg": str(e)}],
                user_id=record.get("user_id"),
            ))
            logger.error(
                "Unexpected user validation error | row=%d | user_id=%s",
                idx, record.get("user_id", "N/A"),
                exc_info=True
            )

    logger.info(
        "User validation: %d valid, %d invalid",
        len(valid_records), len(invalid_records)
    )

    return valid_records, invalid_records


# ============================================================
# REVIEW VALIDATION
# ============================================================

def validate_review_data(
        raw_records: List[Dict[str, Any]]
) -> Tuple[List[Review], List[Dict[str, Any]]]:
    valid_records: List[Review] = []
    invalid_records: List[Dict[str, Any]] = []

    for idx, record in enumerate(raw_records, start=1):
        try:
            valid_records.append(Review(**record))

        except ValidationError as e:
            invalid_records.append(_create_error_record(
                row_number=idx,
                entity="Review",
                record=record,
                errors=e.errors(),
                review_id=record.get("review_id"),
                user_id=record.get("user_id"),
                business_id=record.get("business_id"),
            ))
            logger.warning(
                "Review validation failed | row=%d | review_id=%s",
                idx, record.get("review_id", "N/A")
            )

        except Exception as e:
            invalid_records.append(_create_error_record(
                row_number=idx,
                entity="Review",
                record=record,
                errors=[{"type": "unexpected", "msg": str(e)}],
                review_id=record.get("review_id"),
            ))
            logger.error(
                "Unexpected review validation error | row=%d | review_id=%s",
                idx, record.get("review_id", "N/A"),
                exc_info=True
            )

    logger.info(
        "Review validation: %d valid, %d invalid",
        len(valid_records), len(invalid_records)
    )

    return valid_records, invalid_records


# ============================================================
# CATEGORY VALIDATION (Raw CSV rows)
# ============================================================

def validate_category_data(
        raw_records: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Validate category CSV rows (business_id, category).

    Returns validated raw rows (not Category models) since Category
    nodes are created during normalization from these rows.
    """

    valid_records: List[Dict[str, Any]] = []
    invalid_records: List[Dict[str, Any]] = []

    for idx, record in enumerate(raw_records, start=1):
        business_id = record.get("business_id")
        raw_category_name = record.get("category")
        errors = []

        # Validate business_id (still manual as it's not part of the Category model)
        if not business_id:
            errors.append({"type": "missing_field", "msg": "Missing business_id", "loc": ["business_id"]})
        elif not isinstance(business_id, str):
            errors.append({"type": "invalid_type", "msg": f"business_id must be string, got {type(business_id)}", "loc": ["business_id"]})
        elif not business_id.strip():
            errors.append({"type": "empty_field", "msg": "business_id is empty", "loc": ["business_id"]})

        # Validate category using the Pydantic Category model
        category_model = None
        if raw_category_name is None:
            errors.append({"type": "missing_field", "msg": "Missing category", "loc": ["category"]})
        else:
            try:
                # Use the Category model to validate and clean the category name
                category_model = Category(name=raw_category_name)
            except ValidationError as e:
                # Add Pydantic validation errors to our errors list
                for err in e.errors():
                    # Prefix 'category' to the location if it's not already there
                    loc = list(err.get("loc", []))
                    if not loc or loc[0] != "category":
                        loc.insert(0, "category")
                    err["loc"] = loc
                    errors.append(err)
            except Exception as e:
                errors.append({"type": "unexpected", "msg": str(e), "loc": ["category"]})


        if errors:
            invalid_records.append(_create_error_record(
                row_number=idx,
                entity="Category",
                record=record,
                errors=errors,
                business_id=business_id,
                category_name=raw_category_name,
            ))
            logger.warning(
                "Category validation failed | row=%d | business_id=%s | category=%s | errors=%d",
                idx, business_id, raw_category_name, len(errors)
            )
        else:
            # If valid, append the cleaned business_id and category name
            valid_records.append({
                "business_id": business_id.strip(),
                "category": category_model.name if category_model else raw_category_name.strip(), # Use cleaned name
            })

    logger.info(
        "Category validation: %d valid, %d invalid",
        len(valid_records), len(invalid_records)
    )

    return valid_records, invalid_records


# ============================================================
# FRIEND VALIDATION
# ============================================================

def validate_friend_data(
        raw_records: List[Dict[str, Any]]
) -> Tuple[List[Friend], List[Dict[str, Any]]]:
    valid_records: List[Friend] = []
    invalid_records: List[Dict[str, Any]] = []

    for idx, record in enumerate(raw_records, start=1):
        try:
            valid_records.append(Friend(**record))

        except ValidationError as e:
            invalid_records.append(_create_error_record(
                row_number=idx,
                entity="Friend",
                record=record,
                errors=e.errors(),
                user1=record.get("user1"),
                user2=record.get("user2"),
            ))
            logger.warning(
                "Friend validation failed | row=%d | users=%s,%s",
                idx, record.get("user1", "N/A"), record.get("user2", "N/A")
            )

        except Exception as e:
            invalid_records.append(_create_error_record(
                row_number=idx,
                entity="Friend",
                record=record,
                errors=[{"type": "unexpected", "msg": str(e)}],
                user1=record.get("user1"),
                user2=record.get("user2"),
            ))
            logger.error(
                "Unexpected friend validation error | row=%d | users=%s,%s",
                idx, record.get("user1", "N/A"), record.get("user2", "N/A"),
                exc_info=True
            )

    logger.info(
        "Friend validation: %d valid, %d invalid",
        len(valid_records), len(invalid_records)
    )

    return valid_records, invalid_records




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

