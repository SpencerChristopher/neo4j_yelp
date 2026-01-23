from typing import List, Dict, Any, Tuple
from pydantic import ValidationError
from src.models.business import Business
from src.models.user import User
from src.models.canonical_city_state import CanonicalCityState
import logging

logger = logging.getLogger(__name__)


# ============================================================
# Business validation
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
            invalid_records.append({
                "row_number": idx,
                "entity": "Business",
                "business_id": record.get("business_id"),
                "errors": e.errors(),
                "record": record,
            })

            logger.warning(
                "Business validation failed | row=%s | business_id=%s | errors=%d",
                idx,
                record.get("business_id"),
                len(e.errors()),
            )

        except Exception as e:
            invalid_records.append({
                "row_number": idx,
                "entity": "Business",
                "business_id": record.get("business_id"),
                "errors": [{"msg": str(e)}],
                "record": record,
            })

            logger.error(
                "Unexpected business validation error | row=%s | business_id=%s",
                idx,
                record.get("business_id"),
                exc_info=True,
            )

    logger.info(
        "Business validation complete | valid=%d | invalid=%d",
        len(valid_records),
        len(invalid_records),
    )

    return valid_records, invalid_records


# ============================================================
# Canonical City / State validation
# ============================================================

def validate_canonical_city_state_data(
    raw_records: List[Dict[str, Any]]
) -> Tuple[List[CanonicalCityState], List[Dict[str, Any]]]:

    valid_records: List[CanonicalCityState] = []
    invalid_records: List[Dict[str, Any]] = []

    for idx, record in enumerate(raw_records, start=1):
        try:
            valid_records.append(CanonicalCityState(**record))

        except ValidationError as e:
            invalid_records.append({
                "row_number": idx,
                "entity": "CanonicalCityState",
                "city": record.get("city"),
                "state_code": record.get("state_code"),
                "errors": e.errors(),
                "record": record,
            })

            logger.warning(
                "Canonical city-state validation failed | row=%s | city=%s | state=%s | errors=%d",
                idx,
                record.get("city"),
                record.get("state_code"),
                len(e.errors()),
            )

        except Exception as e:
            invalid_records.append({
                "row_number": idx,
                "entity": "CanonicalCityState",
                "errors": [{"msg": str(e)}],
                "record": record,
            })

            logger.error(
                "Unexpected canonical city-state validation error | row=%s",
                idx,
                exc_info=True,
            )

    logger.info(
        "Canonical city-state validation complete | valid=%d | invalid=%d",
        len(valid_records),
        len(invalid_records),
    )

    return valid_records, invalid_records

def validate_user_data(
    raw_records: list[dict]
) -> tuple[list[User], list[dict]]:

    valid, invalid = [], []

    for i, record in enumerate(raw_records):
        try:
            user = User(**record)
            valid.append(user)
        except ValidationError as e:
            invalid.append({
                "original_record": record,
                "error": str(e)
            })
            logger.warning(
                f"User validation failed row {i+1}: "
                f"{record.get('user_id', 'N/A')}"
            )

    logger.info(
        f"User validation complete: {len(valid)} valid, "
        f"{len(invalid)} invalid"
    )
    return valid, invalid
