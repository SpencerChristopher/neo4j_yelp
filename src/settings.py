from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, BaseModel
from typing import Callable, Type, Optional


class PhaseConfig(BaseModel):
    name: str
    csv_file_name: str # Changed from Path to str
    chunk_size: int
    validator_func_name: str  # Name of the validation function from src.validator
    normalizer_func_name: str  # Name of the normalization function from src.normalizer
    loader_method_name: str  # Name of the method on Neo4jLoader to call (e.g., 'load_users')
    model_name: str  # Name of the Pydantic model (e.g., 'User')
    node_label: Optional[str] = None # Added field
    id_property: Optional[str] = None # Added field

class PipelineConfig(BaseModel):
    phases: list[PhaseConfig]
    dead_letter_max_records_per_batch: int = 500

class Settings(BaseSettings):
    # Pydantic-settings will automatically load environment variables from .env
    # and respect prefixes (e.g., NEO4J_URI, APP_NAME_NEO4J_URI)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Neo4j Credentials
    NEO4J_URI: str = Field("bolt://127.0.0.1:7687", description="Neo4j connection URI")
    NEO4J_USER: str = Field(..., description="Neo4j username")
    NEO4J_PASSWORD: str = Field(..., description="Neo4j password")
    
    # Neo4j Read-only User Credentials
    NEO4J_READ_USER: str = Field(..., description="Neo4j read-only username")
    NEO4J_READ_PASSWORD: str = Field(..., description="Neo4j read-only password")

    # Data File Paths
    DATA_DIR: Path = Field(Path("Data"), description="Directory containing source data files")
    NEO4J_IMPORT_SUBDIR: str = Field("", description="Subdirectory under Neo4j import root for LOAD CSV (e.g., 'test_data')")
    BUSINESS_CSV: Path = Field(Path("business_small.csv"), description="Filename for business data")
    BUSINESS_CITY_CSV: Path = Field(Path("business_city.csv"), description="Filename for business city data")
    REVIEW_CSV: Path = Field(Path("review_small.csv"), description="Filename for review data")
    USER_CSV: Path = Field(Path("user_small.csv"), description="Filename for user data")
    CATEGORY_CSV: Path = Field(Path("business_categories_small.csv"), description="Filename for category data")
    FRIEND_CSV: Path = Field(Path("user_friendship.csv"), description="Filename for user friendship data")

    # ETL Configuration
    BATCH_SIZE: int = Field(500, description="Batch size for database operations")
    LOG_FILE: Path = Field(Path("logs/elt_process.log"), description="Path for the ETL process log file")
    DEAD_LETTER_FILE: Path = Field(Path("logs/dead_letters.jsonl"), description="Path for the dead letter queue file")

    NEO4J_CONSTRAINTS_AND_INDEXES: list[str] = Field(
        [
            # --- Business ---
            "CREATE CONSTRAINT business_id_unique IF NOT EXISTS "
            "FOR (b:Business) REQUIRE b.business_id IS UNIQUE",

            "CREATE INDEX business_name_idx IF NOT EXISTS "
            "FOR (b:Business) ON (b.name)",

            # --- User ---
            "CREATE CONSTRAINT user_id_unique IF NOT EXISTS "
            "FOR (u:User) REQUIRE u.user_id IS UNIQUE",

            "CREATE INDEX user_name_idx IF NOT EXISTS "
            "FOR (u:User) ON (u.name)",

            # --- Review ---
            "CREATE CONSTRAINT review_id_unique IF NOT EXISTS "
            "FOR (r:Review) REQUIRE r.review_id IS UNIQUE",

            "CREATE INDEX review_date_idx IF NOT EXISTS "
            "FOR (r:Review) ON (r.date)",

            # --- State ---
            "CREATE CONSTRAINT state_code_unique IF NOT EXISTS "
            "FOR (s:State) REQUIRE s.code IS UNIQUE",

            # --- City ---
            "CREATE CONSTRAINT city_name_state_unique IF NOT EXISTS "
            "FOR (c:City) REQUIRE (c.name, c.state_code) IS UNIQUE",

            # --- Postal Code ---
            "CREATE CONSTRAINT postal_code_unique IF NOT EXISTS "
            "FOR (p:PostalCode) REQUIRE p.code IS UNIQUE",

            # --- Category ---
            "CREATE CONSTRAINT category_name_unique IF NOT EXISTS "
            "FOR (c:Category) REQUIRE c.name IS UNIQUE"
        ],
        description="Cypher statements to create constraints and indexes in Neo4j"
    )

    pipeline: PipelineConfig = Field(
        default_factory=lambda: PipelineConfig(
            phases=[
                PhaseConfig( # New Canonical City/State Phase - Moved up
                    name="Canonical City/State",
                    csv_file_name=str(Path("business_city.csv")),
                    chunk_size=100, # Assuming business_city.csv is small
                    validator_func_name="validate_city_state_data",
                    normalizer_func_name="normalize_canonical_city_state_data",
                    loader_method_name="load_nodes_and_relationships",
                    model_name="City",
                    node_label="City",
                    id_property="name"
                ),
                PhaseConfig(
                    name="Businesses with Geographic Relationships",
                    csv_file_name=str(Path("business_small.csv")),
                    chunk_size=200,
                    validator_func_name="validate_business_data",
                    normalizer_func_name="normalize_business_data",
                    loader_method_name="process_business_data",
                    model_name="Business",
                    node_label="Business",
                    id_property="business_id"
                ),
                PhaseConfig(
                    name="Categories and Business-Category Relationships",
                    csv_file_name=str(Path("business_categories_small.csv")),
                    chunk_size=1000,
                    validator_func_name="validate_category_data",
                    normalizer_func_name="normalize_category_data",
                    loader_method_name="load_nodes",
                    model_name="Category",
                    node_label="Category",
                    id_property="name"
                ),
                PhaseConfig(
                    name="Users",
                    csv_file_name=str(Path("user_small.csv")),
                    chunk_size=500,
                    validator_func_name="validate_user_data",
                    normalizer_func_name="normalize_user_data",
                    loader_method_name="load_nodes",
                    model_name="User",
                    node_label="User",
                    id_property="user_id"
                ),
                PhaseConfig(
                    name="Reviews with Immediate User/Business Relationships",
                    csv_file_name=str(Path("review_small.csv")),
                    chunk_size=300,
                    validator_func_name="validate_review_data",
                    normalizer_func_name="normalize_review_data",
                    loader_method_name="load_nodes",
                    model_name="Review",
                    node_label="Review",
                    id_property="review_id"
                ),
                PhaseConfig( # Friend Relationships - Corrected csv_file_name and kept last
                    name="Friend Relationships",
                    csv_file_name=str(Path("user_friendship.csv")),
                    chunk_size=100, # APOC batch size for friend relationships
                    validator_func_name="none",
                    normalizer_func_name="none",
                    loader_method_name="load_friends_apoc",
                    model_name="Friend",
                    node_label=None,
                    id_property=None
                )
            ],
            dead_letter_max_records_per_batch=500
        ),
        description="Configuration for the ETL pipeline phases"
    )

    def neo4j_import_relative_path(self, csv_file_name: str) -> str:
        """
        Returns the path for Neo4j LOAD CSV relative to the import root.
        """
        subdir = self.NEO4J_IMPORT_SUBDIR.strip().strip("/\\")
        if subdir:
            return f"{subdir}/{csv_file_name}"
        return csv_file_name

    def neo4j_file_url(self, csv_file_name: str) -> str:
        """
        Returns the file URL for Neo4j LOAD CSV.
        """
        return f"file:///{self.neo4j_import_relative_path(csv_file_name)}"

settings = Settings()
