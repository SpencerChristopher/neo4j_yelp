from pathlib import Path
from src.settings import Settings, PhaseConfig, PipelineConfig
from src.pipeline import run_pipeline
from src.loader import Neo4jLoader # Not directly used in run_pipeline, but good for context
import os
from unittest.mock import patch # For monkeypatching settings

# Create a temporary settings object to configure only the desired phases
# This avoids modifying the global settings object for a one-off run
# We copy relevant parts from the global settings to ensure consistency
temp_settings = Settings()
temp_settings.NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j") # Ensure password is set for loader

temp_settings.pipeline = PipelineConfig(
    phases=[
        PhaseConfig( # Canonical City/State
            name="Canonical City/State",
            csv_file_name=Path("business_city.csv"),
            chunk_size=1000, # Using default chunk size
            validator_func_name="validate_city_state_data",
            normalizer_func_name="normalize_canonical_city_state_data",
            loader_method_name="load_nodes_and_relationships",
            model_name="City",
            node_label="City",
            id_property="name"
        ),
        PhaseConfig( # Businesses
            name="Businesses with Geographic Relationships",
            csv_file_name=Path("business_small.csv"),
            chunk_size=1000, # Using default chunk size
            validator_func_name="validate_business_data",
            normalizer_func_name="normalize_business_data",
            loader_method_name="process_business_data",
            model_name="Business",
            node_label="Business",
            id_property="business_id"
        ),
        PhaseConfig( # Categories
            name="Categories and Business-Category Relationships",
            csv_file_name=Path("business_categories_small.csv"),
            chunk_size=1000, # Using default chunk size
            validator_func_name="validate_category_data",
            normalizer_func_name="normalize_category_data",
            loader_method_name="load_nodes",
            model_name="Category",
            node_label="Category",
            id_property="name"
        ),
    ],
    dead_letter_max_records_per_batch=temp_settings.pipeline.dead_letter_max_records_per_batch
)

# Monkeypatch the global settings object for this script's execution
# This is a bit hacky, but needed as run_pipeline uses the global settings
with patch('src.pipeline.settings', new=temp_settings):
    with patch('src.loader.settings', new=temp_settings): # Also patch loader settings
        print("Running pipeline for Business, City/State, and Category data...")
        run_pipeline()
        print("Pipeline execution complete.")

print("\n--- Verification ---")
print("To verify the loaded data, connect to your Neo4j instance (e.g., Neo4j Browser at http://localhost:7474) and run the following Cypher queries:")
print("\nNode Counts:")
print("MATCH (n) RETURN labels(n) AS Label, count(n) AS Count")
print("\nRelationship Counts:")
print("MATCH ()-[r]->() RETURN type(r) AS Type, count(r) AS Count")
print("\nSpecific Checks (Expected vs. Actual):")
print(f"  Expected {1258} City nodes: MATCH (c:City) RETURN count(c)")
print(f"  Expected {36} State nodes: MATCH (s:State) RETURN count(s)")
print(f"  Expected {63896} Business nodes: MATCH (b:Business) RETURN count(b)")
print(f"  Expected {2889} PostalCode nodes (unique from Business data): MATCH (pc:PostalCode) RETURN count(pc)")
print(f"  Expected {1230} Category nodes: MATCH (cat:Category) RETURN count(cat)")
print(f"  Expected {1258} CLAIMS_STATE relationships (City->State): MATCH (:City)-[r:CLAIMS_STATE]->(:State) RETURN count(r)")
print(f"  Expected {63896} LOCATED_NEAR relationships (Business->City): MATCH (:Business)-[r:LOCATED_NEAR]->(:City) RETURN count(r)")
print(f"  Expected {63896} CLAIMS_STATE relationships (Business->State, from Business normalization): MATCH (:Business)-[r:CLAIMS_STATE]->(:State) RETURN count(r)")
print(f"  Expected {63896} CLAIMS_POSTAL_CODE relationships (Business->PostalCode): MATCH (:Business)-[r:CLAIMS_POSTAL_CODE]->(:PostalCode) RETURN count(r)")
print(f"  Expected {267467} CLAIMS_CATEGORY relationships (Business->Category): MATCH (:Business)-[r:CLAIMS_CATEGORY]->(:Category) RETURN count(r)")
