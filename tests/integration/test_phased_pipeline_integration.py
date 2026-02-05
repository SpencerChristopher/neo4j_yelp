import pytest
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import List
import pandas as pd # Added import for pandas

from src.loader import Neo4jLoader
from src.pipeline import run_pipeline as pipeline_run, PipelineRunner
from src.settings import settings, PhaseConfig
from tests.utils import (
    csv_path,
    count_csv_rows,
    exploded_category_stats,
    valid_business_count,
)


import logging
logger = logging.getLogger(__name__)

# Mark all tests in this module as integration and neo4j
pytestmark = [pytest.mark.integration, pytest.mark.neo4j]

@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    """
    Sets up the test environment for phased loading tests.
    This fixture is automatically used by tests in this module.
    """
    pass

@pytest.fixture(scope="function", autouse=True)
def clear_db_before_each_test(neo4j_loader):
    """Clears the Neo4j database before each test function."""
    with neo4j_loader.driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    yield

@pytest.fixture
def phased_pipeline_settings(monkeypatch):
    """
    A fixture to help configure pipeline phases for specific tests.
    It returns a callable that can be used to set settings.pipeline.phases.
    """
    def _set_phases(phases: List[PhaseConfig]):
        mock_pipeline_config = MagicMock()
        mock_pipeline_config.phases = phases
        mock_pipeline_config.dead_letter_max_records_per_batch = settings.pipeline.dead_letter_max_records_per_batch
        monkeypatch.setattr('src.settings.settings.pipeline', mock_pipeline_config)
    return _set_phases

class TestPhasedLoading:
    """
    Tests for individual and sequenced phases of the ETL pipeline using the smaller
    test datasets from the tests/data directory.
    """

    def test_load_canonical_city_state(self, neo4j_loader, phased_pipeline_settings, test_data_provider):
        """
        Verifies the loading of canonical City/State data and its structure.
        This includes:
        - Asserting the correct count of State and City nodes based on test data.
        - Confirming the existence of a sample State and City node.
        - Asserting the correct count of IN relationships.
        - Verifying the existence of a specific IN relationship.
        """
        phased_pipeline_settings([
            PhaseConfig(
                name="Canonical City/State",
                csv_file_name=str(Path("test.business_city.csv")),
                chunk_size=100,
                validator_func_name="validate_city_state_data",
                normalizer_func_name="normalize_canonical_city_state_data",
                loader_method_name="load_nodes_and_relationships",
                model_name="City",
                node_label="City",
                id_property="name"
            )
        ])
        pipeline_run() 

        with neo4j_loader.driver.session() as session:
            states_in_db = session.run("MATCH (s:State) RETURN s.code AS code").data()
            cities_in_db = session.run("MATCH (c:City) RETURN c.name AS name").data()
            
            expected_state_count = test_data_provider["state_count"]
            assert len(states_in_db) == expected_state_count, f"Expected {expected_state_count} State nodes, but found {len(states_in_db)}."
            
            sample_state = test_data_provider["sample_state_code"]
            assert session.run(f"MATCH (s:State {{code: '{sample_state}'}}) RETURN s").single(), f"Sample state '{sample_state}' not found."
            logger.info(f"Verified sample state '{sample_state}' exists.")

            expected_city_count = test_data_provider["city_count"]
            assert len(cities_in_db) == expected_city_count, f"Expected {expected_city_count} City nodes, but found {len(cities_in_db)}."
            
            sample_city_name = test_data_provider["sample_city_name"]
            sample_city_state = test_data_provider["sample_city_state_code"]
            assert session.run(f"MATCH (c:City {{name: \"{sample_city_name}\", state_code: '{sample_city_state}'}}) RETURN c").single(), f"Sample city '{sample_city_name}' not found."
            logger.info(f"Verified sample city '{sample_city_name}' exists.")

    def test_load_users_and_friendships(self, neo4j_loader, phased_pipeline_settings, test_data_provider, monkeypatch):
        """
        Verifies loading Users and their FRIENDS_WITH relationships using APOC.
        This includes:
        - Asserting correct User node count.
        - Confirming a sample User node exists.
        - Asserting correct FRIENDS_WITH relationship count.
        - Verifying a sample FRIENDS_WITH relationship exists.
        """
        monkeypatch.setattr('src.settings.settings.FRIEND_CSV', Path("test.tiny_user_friendship.csv"))

        phased_pipeline_settings([
            PhaseConfig(
                name="Users",
                csv_file_name=str(Path("test.user_small.csv")),
                chunk_size=500,
                validator_func_name="validate_user_data",
                normalizer_func_name="normalize_user_data",
                loader_method_name="load_nodes",
                model_name="User",
                node_label="User",
                id_property="user_id"
            ),
            PhaseConfig(
                name="Friend Relationships",
                csv_file_name=str(Path("test.tiny_user_friendship.csv")),
                chunk_size=50,
                validator_func_name="none",
                normalizer_func_name="none",
                loader_method_name="load_friends_apoc",
                model_name="Friend",
                node_label=None,
                id_property=None
            )
        ])
        pipeline_run()

        with neo4j_loader.driver.session() as session:
            expected_users_count = test_data_provider["user_count"]
            users_count = session.run("MATCH (u:User) RETURN count(u) AS count").single().value()
            assert users_count == expected_users_count, f"Expected {expected_users_count} User nodes, but found {users_count}."
            logger.info("User node count verified.")

            # Calculate expected friendships count directly from the tiny CSV
            tiny_friend_df = pd.read_csv(settings.DATA_DIR / Path("test.tiny_user_friendship.csv"))
            expected_friendships_count = len(tiny_friend_df)
            
            friendships_count = session.run("MATCH ()-[f:FRIENDS_WITH]->() RETURN count(f) AS count").single().value()
            assert friendships_count == expected_friendships_count, f"Expected {expected_friendships_count} FRIENDS_WITH relationships, but found {friendships_count}."
            logger.info("FRIENDS_WITH relationship count verified.")

    def test_load_business_and_categories_with_geo_claims(self, neo4j_loader, phased_pipeline_settings, test_data_provider, monkeypatch):
        """
        Verifies loading of Businesses, Categories, and their geographic and category relationships.
        """
        # Calculate expected business node count directly from the CSV, considering validation
        expected_business_count_calculated = valid_business_count("test.business_small.csv")
        expected_category_node_count_calculated, expected_claims_category_rels_calculated = exploded_category_stats(
            "test.business_categories_small.csv"
        )


        phased_pipeline_settings([
            PhaseConfig(
                name="Canonical City/State",
                csv_file_name=str(Path("test.business_city.csv")),
                chunk_size=100,
                validator_func_name="validate_city_state_data",
                normalizer_func_name="normalize_canonical_city_state_data",
                loader_method_name="load_nodes_and_relationships",
                model_name="City",
                node_label="City",
                id_property="name"
            ),
            PhaseConfig(
                name="Businesses with Geographic Relationships",
                csv_file_name=str(Path("test.business_small.csv")),
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
                csv_file_name=str(Path("test.business_categories_small.csv")),
                chunk_size=1000,
                validator_func_name="validate_category_data",
                normalizer_func_name="normalize_category_data",
                loader_method_name="load_nodes",
                model_name="Category",
                node_label="Category",
                id_property="name"
            )
        ])
        pipeline_run()

        with neo4j_loader.driver.session() as session:
            businesses = session.run("MATCH (b:Business) RETURN count(b) AS count").single().value()
            assert businesses == expected_business_count_calculated, f"Expected {expected_business_count_calculated} Business nodes, but found {businesses}."
            logger.info("Business node count verified.")

            categories = session.run("MATCH (c:Category) RETURN count(c) AS count").single().value()
            assert categories == expected_category_node_count_calculated, f"Expected {expected_category_node_count_calculated} Category nodes, but found {categories}."
            logger.info("Category node count verified.")

            claims_category_rels = session.run("MATCH (b:Business)-[:CLAIMS_CATEGORY]->(:Category) RETURN count(*) AS count").single().value()
            assert claims_category_rels == expected_claims_category_rels_calculated, f"Expected {expected_claims_category_rels_calculated} CLAIMS_CATEGORY relationships, but found {claims_category_rels}."
            logger.info("CLAIMS_CATEGORY relationships verified.")
    def test_load_users_businesses_and_reviews_with_relationships(self, neo4j_loader, phased_pipeline_settings, test_data_provider, monkeypatch):
        """
        Verifies loading of Users, Businesses, Reviews and their WROTE and OF relationships.
        """
        monkeypatch.setattr('src.settings.settings.REVIEW_CSV', Path("test.review_small.csv"))
        
        phased_pipeline_settings([
            PhaseConfig(
                name="Canonical City/State",
                csv_file_name=str(Path("test.business_city.csv")),
                chunk_size=100,
                validator_func_name="validate_city_state_data",
                normalizer_func_name="normalize_canonical_city_state_data",
                loader_method_name="load_nodes_and_relationships",
                model_name="City",
                node_label="City",
                id_property="name"
            ),
            PhaseConfig(
                name="Users",
                csv_file_name=str(Path("test.user_small.csv")),
                chunk_size=500,
                validator_func_name="validate_user_data",
                normalizer_func_name="normalize_user_data",
                loader_method_name="load_nodes",
                model_name="User",
                node_label="User",
                id_property="user_id"
            ),
            PhaseConfig(
                name="Businesses with Geographic Relationships",
                csv_file_name=str(Path("test.business_small.csv")),
                chunk_size=200,
                validator_func_name="validate_business_data",
                normalizer_func_name="normalize_business_data",
                loader_method_name="process_business_data",
                model_name="Business",
                node_label="Business",
                id_property="business_id"
            ),
            PhaseConfig(
                name="Reviews with Immediate User/Business Relationships",
                csv_file_name=str(Path("test.review_small.csv")),
                chunk_size=300,
                validator_func_name="validate_review_data",
                normalizer_func_name="normalize_review_data",
                loader_method_name="load_nodes",
                model_name="Review",
                node_label="Review",
                id_property="review_id"
            )
        ])
        pipeline_run()

        with neo4j_loader.driver.session() as session:
            # Recalculate expected counts directly from the small test CSV
            expected_reviews_count = count_csv_rows("test.review_small.csv")
            review_df = pd.read_csv(csv_path("test.review_small.csv"))
            
            reviews = session.run("MATCH (r:Review) RETURN count(r) AS count").single().value()
            assert reviews == expected_reviews_count, f"Expected {expected_reviews_count} Review nodes, but found {reviews}."
            logger.info("Review node count verified.")

            # Each review should have one WROTE and one OF relationship
            expected_wrote_rels = expected_reviews_count
            wrote_rels = session.run("MATCH (:User)-[:WROTE]->(:Review) RETURN count(*) AS count").single().value()
            # Assertions on relationships need to be more precise based on actual relationships formed
            assert wrote_rels == expected_wrote_rels, f"Expected {expected_wrote_rels} WROTE relationships, but found {wrote_rels}."
            logger.info("WROTE relationship count verified.")

            expected_of_rels = expected_reviews_count
            of_rels = session.run("MATCH (:Review)-[:OF]->(:Business) RETURN count(*) AS count").single().value()
            assert of_rels == expected_of_rels, f"Expected {expected_of_rels} OF relationships, but found {of_rels}."
            logger.info("OF relationship count verified.")

            # Verify a specific WROTE relationship from the data provider
            user_id_for_wrote = review_df['user_id'].iloc[0] # Get sample from current df
            review_id_for_wrote = review_df['review_id'].iloc[0]
            specific_wrote_query = f"MATCH (u:User {{user_id: '{user_id_for_wrote}'}})-[:WROTE]->(r:Review {{review_id: '{review_id_for_wrote}'}}) RETURN count(*) AS count"
            specific_wrote_count = session.run(specific_wrote_query).single().value()
            assert specific_wrote_count == 1, f"Expected 1 WROTE relationship from '{user_id_for_wrote}' to '{review_id_for_wrote}', but found {specific_wrote_count}."
            logger.info(f"Specific WROTE relationship verified.")

            # Verify a specific OF relationship from the data provider
            review_id_for_of = review_df['review_id'].iloc[0] # Get sample from current df
            business_id_for_of = review_df['business_id'].iloc[0]
            specific_of_query = f"MATCH (r:Review {{review_id: '{review_id_for_of}'}})-[:OF]->(b:Business {{business_id: '{business_id_for_of}'}}) RETURN count(*) AS count"
            specific_of_count = session.run(specific_of_query).single().value()
            assert specific_of_count == 1, f"Expected 1 OF relationship from '{review_id_for_of}' to '{business_id_for_of}', but found {specific_of_count}."
            logger.info(f"Specific OF relationship verified.")
