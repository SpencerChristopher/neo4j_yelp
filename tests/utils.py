from pathlib import Path
import pandas as pd
from src.settings import settings


def csv_path(filename: str) -> Path:
    return Path(settings.DATA_DIR) / Path(filename)


def csv_chunks(filename: str, chunksize: int | None = None):
    size = chunksize or settings.BATCH_SIZE
    return pd.read_csv(csv_path(filename), chunksize=size)


def count_csv_rows(filename: str, chunksize: int | None = None) -> int:
    return sum(len(chunk) for chunk in csv_chunks(filename, chunksize=chunksize))


def exploded_category_stats(filename: str, chunksize: int | None = None) -> tuple[int, int]:
    unique_categories: set[str] = set()
    total_exploded = 0
    for chunk in csv_chunks(filename, chunksize=chunksize):
        exploded = chunk["category"].str.split(",").explode().str.strip().dropna()
        unique_categories.update(exploded.tolist())
        total_exploded += len(exploded)
    return len(unique_categories), total_exploded


def valid_business_count(filename: str, chunksize: int | None = None) -> int:
    from src.validator import validate_business_data
    from src.models.business import Business

    total_valid = 0
    for chunk in csv_chunks(filename, chunksize=chunksize):
        records = chunk.to_dict(orient="records")
        valid_records, _ = validate_business_data(records, Business, "Business", "business_id")
        total_valid += len(valid_records)
    return total_valid
