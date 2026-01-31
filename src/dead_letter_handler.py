# src/dead_letter_handler.py
import json
import logging
import os
from typing import Any, Dict
from pathlib import Path

from pydantic import BaseModel

from src.settings import settings

logger = logging.getLogger(__name__)

def _default_json_serializer(obj):
    """Helper to serialize non-JSON-serializable objects (like Exceptions, Paths, Pydantic models)."""
    if isinstance(obj, (Path, Exception)):
        return str(obj)
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

def _standardize_error(error_item: Any) -> Dict[str, Any]:
    """Standardize a single error item into a serializable dictionary."""
    if isinstance(error_item, Exception):
        return {"type": type(error_item).__name__, "msg": str(error_item)}
    elif isinstance(error_item, dict):
        return error_item  # Assume Pydantic error dicts are already serializable
    else:
        return {"type": "unknown_error_format", "msg": str(error_item)}

def write_dead_letters(records, max_records_per_batch: int = 500):
    """Write validation errors to dead letter queue with robust serialization."""
    if not records:
        return

    os.makedirs(os.path.dirname(settings.DEAD_LETTER_FILE), exist_ok=True) # Ensure directory exists

    with open(settings.DEAD_LETTER_FILE, "a", encoding="utf-8") as f:
        for r in records[:max_records_per_batch]:
            serializable_record = r.copy()

            # Standardize 'errors' field to be a list of serializable dicts
            if "errors" in serializable_record:
                errors_raw = serializable_record["errors"]
                processed_errors = []
                if not isinstance(errors_raw, list):
                    errors_raw = [errors_raw] # Ensure it's always iterable
                processed_errors = [_standardize_error(err_item) for err_item in errors_raw]
                serializable_record["errors"] = processed_errors

            # Truncate record data
            if "record" in serializable_record and isinstance(serializable_record["record"], dict):
                serializable_record["record"] = {
                    k: str(v)[:200] if not isinstance(v, (int, float, bool, type(None))) else v
                    for k, v in serializable_record["record"].items()
                }

            try:
                f.write(json.dumps(serializable_record, ensure_ascii=False, default=_default_json_serializer) + "\n")
            except Exception as e:
                logger.error(f"Failed to serialize record to dead letter: {serializable_record} - {e}", exc_info=True)
                f.write(json.dumps({"unserializable_record_fallback": str(serializable_record), "error": str(e)}, ensure_ascii=False) + "\n")
