from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    # Pydantic-settings will automatically load environment variables from .env
    # and respect prefixes (e.g., NEO4J_URI, APP_NAME_NEO4J_URI)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Neo4j Credentials
    NEO4J_URI: str = Field("bolt://localhost:7687", description="Neo4j connection URI")
    NEO4J_USER: str = Field("neo4j", description="Neo4j username")
    NEO4J_PASSWORD: str | None = Field(None, description="Neo4j password")

    # Data File Paths
    DATA_DIR: Path = Field(Path("Data"), description="Directory containing source data files")
    BUSINESS_CSV: Path = Field(Path("business_small.csv"), description="Filename for business data")
    BUSINESS_CITY_CSV: Path = Field(Path("business_city.csv"), description="Filename for business city data")
    REVIEW_CSV: Path = Field(Path("review_small.csv"), description="Filename for review data")
    USER_CSV: Path = Field(Path("user_small.csv"), description="Filename for user data")
    CATEGORY_CSV: Path = Field(Path("business_categories_small.csv"), description="Filename for category data")
    FRIEND_CSV: Path = Field(Path("user_friendship.csv"), description="Filename for user friendship data")

    # ETL Configuration
    BATCH_SIZE: int = Field(1000, description="Batch size for database operations")
    LOG_FILE: Path = Field(Path("logs/elt_process.log"), description="Path for the ETL process log file")
    DEAD_LETTER_FILE: Path = Field(Path("logs/dead_letters.jsonl"), description="Path for the dead letter queue file")


settings = Settings()

