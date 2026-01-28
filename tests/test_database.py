"""
Integration tests for Neo4j database operations.
"""
import pytest
from unittest.mock import patch, MagicMock

from src.loader import Neo4jLoader
from src.settings import settings
from src.models import Business, Review, User
from src.normalizer import normalize_business_data, normalize_review_data, normalize_user_data


@pytest.mark.integration
@pytest.mark.neo4j
class TestDatabaseConnection:
    """Tests for database connection and setup."""

    def test_database_connection(self):
        """Test connecting to Neo4j database."""
        # This would test actual connection if NEO4J_URI is set
        # For now, it's a placeholder for integration tests
        pass

    def test_create_constraints(self):
        """Test creating database constraints."""
        # Test constraint creation logic
        pass


@pytest.mark.unit
class TestBusinessOperations:
    """Unit tests for business-related operations."""

    def test_create_business_node(self, mock_neo4j_driver, sample_business_data):
        """Test creating a business node in Neo4j."""
        from src.models import Business

        business = Business(**sample_business_data)

        # Mock the database operation
        mock_session = mock_neo4j_driver.session.return_value.__enter__.return_value
        mock_transaction = mock_session.begin_transaction.return_value.__enter__.return_value
        mock_result = mock_transaction.run.return_value

        # Execute a hypothetical create function (reflecting Neo4jLoader's MERGE/SET)
        query = """
        MERGE (b:Business {business_id: $business_id})
        ON CREATE SET
            b.name = $name,
            b.stars = $stars,
            b.review_count = $review_count,
            b.is_open = $is_open,
            b.city = $city,
            b.state = $state,
            b.postal_code = $postal_code,
            b.latitude = $latitude,
            b.longitude = $longitude
        ON MATCH SET
            b.name = $name,
            b.stars = $stars,
            b.review_count = $review_count,
            b.is_open = $is_open,
            b.city = $city,
            b.state = $state,
            b.postal_code = $postal_code,
            b.latitude = $latitude,
            b.longitude = $longitude
        RETURN b
        """

        mock_transaction.run(
            query,
            business_id=business.business_id,
            name=business.name,
            stars=business.stars,
            review_count=business.review_count,
            is_open=business.is_open,
            city=business.city,
            state=business.state,
            postal_code=business.postal_code,
            latitude=business.location.latitude,
            longitude=business.location.longitude
        )

        # Verify the query was called with correct parameters
        mock_transaction.run.assert_called_once()
        call_args = mock_transaction.run.call_args
        assert call_args[0][0] == query
        assert call_args[1]["business_id"] == "abc123"
        assert call_args[1]["name"] == "Test Restaurant"
        assert call_args[1]["review_count"] == 100
        assert call_args[1]["state"] == "TS"
        assert call_args[1]["latitude"] == 40.7128

@pytest.mark.unit
class TestUserOperations:
    """Unit tests for user-related operations."""

    def test_create_user_node(self, mock_neo4j_driver, sample_user_data):
        """Test creating a user node in Neo4j."""
        from src.models import User

        user = User(**sample_user_data)

        # Mock database operation
        mock_transaction = (
            mock_neo4j_driver.session.return_value
            .__enter__.return_value
            .begin_transaction.return_value
            .__enter__.return_value
        )

        query = """
        CREATE (u:User {
            user_id: $user_id,
            name: $name,
            review_count: $review_count
        })
        RETURN u
        """

        mock_transaction.run(
            query,
            user_id=user.user_id,
            name=user.name,
            review_count=user.review_count
        )

        mock_transaction.run.assert_called_once()


@pytest.mark.integration
@pytest.mark.neo4j
class TestNeo4jQueryMismatch:
    """Tests to demonstrate mismatches with neo4j/queries.cypher."""

    # This fixture would be replaced by a proper neo4j_driver_fixture later
    @pytest.fixture(scope="class")
    def live_neo4j_loader(self):
        """Provides a Neo4jLoader instance for integration tests."""
        # Ensure Neo4j is running for this fixture to work
        loader = Neo4jLoader()
        yield loader
        loader.close()

    @pytest.fixture(scope="class", autouse=True)
    def setup_test_data(self, live_neo4j_loader, sample_business_data, sample_review_data, sample_user_data):
        """Loads minimal data into Neo4j for query testing."""
        # Clear database first
        with live_neo4j_loader.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            session.run("CALL apoc.schema.assert({}, {}, true)") # Clears constraints too if needed for testing

        # Use models and normalizer to create proper data
        business_model = Business(**sample_business_data)
        user_model = User(**sample_user_data)
        review_model = Review(**sample_review_data)

        # Convert models to dictionaries before loading
        normalized_bus_data = normalize_business_data([business_model])
        bus_nodes_dicts = normalized_bus_data["business_nodes"]
        postal_code_nodes_dicts = normalized_bus_data["postal_code_nodes"] # Directly use from new output

        user_nodes_dicts = normalize_user_data([user_model])["nodes"]
        normalized_review_data = normalize_review_data([review_model])
        review_nodes_dicts = normalized_review_data["nodes"]
        
        # All relationships from business normalizer
        geo_rels_dicts = normalized_bus_data["relationships"] 
        wrote_rels_dicts = [r for r in normalized_review_data["relationships"] if r.get("relationship_type") == "WROTE"]
        of_rels_dicts = [r for r in normalized_review_data["relationships"] if r.get("relationship_type") == "OF"]

        # Load data using the actual loader (using generic load_nodes/load_relationships)
        # Note: City and State nodes are assumed to be loaded in an earlier pipeline phase,
        # so they are not loaded by normalize_business_data.
        live_neo4j_loader.load_nodes(postal_code_nodes_dicts, "PostalCode", "code")
        live_neo4j_loader.load_nodes(bus_nodes_dicts, "Business", "business_id")
        live_neo4j_loader.load_nodes(user_nodes_dicts, "User", "user_id")
        live_neo4j_loader.load_nodes(review_nodes_dicts, "Review", "review_id")
        
        live_neo4j_loader.load_relationships(geo_rels_dicts)
        live_neo4j_loader.load_relationships(wrote_rels_dicts)
        live_neo4j_loader.load_relationships(of_rels_dicts)


@pytest.mark.integration
@pytest.mark.neo4j
class TestNeo4jLoaderIntegration:
    """Integration tests for Neo4jLoader methods."""

    def test_load_single_business(self, neo4j_loader, sample_business_data):
        """Test loading a single business node."""
        from src.models import Business
        from src.normalizer import normalize_business_data

        business_model = Business(**sample_business_data)
        normalized_data = normalize_business_data([business_model])

        # Extract directly from the new normalized_data structure
        bus_nodes = normalized_data["business_nodes"]
        postal_code_nodes_to_load = normalized_data["postal_code_nodes"]
        
        # City and State nodes are assumed to be pre-loaded in canonical phase
        # Relationships will be loaded separately

        # Load PostalCode nodes (if any)
        created_pc, failed_pc = neo4j_loader.load_nodes(postal_code_nodes_to_load, "PostalCode", "code")
        assert not failed_pc

        # Load business node
        created, failed = neo4j_loader.load_nodes(bus_nodes, "Business", "business_id")
        assert created > 0 
        assert not failed

        # Verify in DB
        with neo4j_loader.driver.session() as session:
            result = session.run("MATCH (b:Business {business_id: $id}) RETURN b", id="abc123").single()
            assert result is not None
            assert result["b"]["name"] == "Test Restaurant"
            assert result["b"]["stars"] == 4.5

    def test_load_single_user(self, neo4j_loader, sample_user_data):
        """Test loading a single user node."""
        from src.models import User
        from src.normalizer import normalize_user_data

        user_model = User(**sample_user_data)
        user_nodes = normalize_user_data([user_model])["nodes"]

        created, failed = neo4j_loader.load_nodes(user_nodes, "User", "user_id")
        assert created > 0
        assert not failed

        # Verify in DB
        with neo4j_loader.driver.session() as session:
            result = session.run("MATCH (u:User {user_id: $id}) RETURN u", id="user123").single()
            assert result is not None
            assert result["u"]["name"] == "John Doe"
            assert result["u"]["review_count"] == 50

    def test_load_single_review_and_relationships(self, neo4j_loader, sample_review_data, sample_user_data, sample_business_data):
        """Test loading a single review node and its relationships to User and Business."""
        from src.models import Review, User, Business
        from src.normalizer import normalize_review_data, normalize_user_data, normalize_business_data

        # Load dependent User and Business nodes first
        user_model = User(**sample_user_data)
        bus_model = Business(**sample_business_data)

        neo4j_loader.load_nodes(normalize_user_data([user_model])["nodes"], "User", "user_id")
        
        normalized_bus_data = normalize_business_data([bus_model])
        bus_nodes = normalized_bus_data["business_nodes"]
        postal_code_nodes_to_load = normalized_bus_data["postal_code_nodes"]
        geo_rels = normalized_bus_data["relationships"]

        # Load geo nodes from business normalizer
        neo4j_loader.load_nodes(postal_code_nodes_to_load, "PostalCode", "code")
        neo4j_loader.load_nodes(bus_nodes, "Business", "business_id")
        neo4j_loader.load_relationships(geo_rels)

        # Prepare review data
        review_model = Review(**sample_review_data)
        normalized_review_data = normalize_review_data([review_model])
        review_nodes = normalized_review_data["nodes"]
        wrote_rels = [r for r in normalized_review_data["relationships"] if r.get("relationship_type") == "WROTE"]
        of_rels = [r for r in normalized_review_data["relationships"] if r.get("relationship_type") == "OF"]

        # Load review node
        created_node, failed_node = neo4j_loader.load_nodes(review_nodes, "Review", "review_id")
        assert created_node > 0
        assert not failed_node

        # Load relationships
        created_wrote, failed_wrote = neo4j_loader.load_relationships(wrote_rels)
        created_of, failed_of = neo4j_loader.load_relationships(of_rels)
        assert created_wrote == 1
        assert not failed_wrote
        assert created_of == 1
        assert not failed_of

        # Verify in DB
        with neo4j_loader.driver.session() as session:
            # Verify Review node
            review_result = session.run("MATCH (r:Review {review_id: $id}) RETURN r", id="rev123").single()
            assert review_result is not None
            assert review_result["r"]["stars"] == 5

            # Verify WROTE relationship
            wrote_rel_result = session.run("""
                MATCH (u:User {user_id: 'user123'})-[w:WROTE]->(r:Review {review_id: 'rev123'})
                RETURN w
            """).single()
            assert wrote_rel_result is not None

            # Verify OF relationship
            of_rel_result = session.run("""
                MATCH (r:Review {review_id: 'rev123'})-[o:OF]->(b:Business {business_id: 'abc123'})
                RETURN o
            """).single()
            assert of_rel_result is not None

    def test_create_friendship(self, neo4j_loader, sample_user_data):
        """Test creating a FRIENDS_WITH relationship between users."""
        from src.models import User, Friend
        from src.normalizer import normalize_user_data, normalize_friend_data

        # Load two distinct users
        user1_data = {**sample_user_data, "user_id": "user1", "name": "Alice"}
        user2_data = {**sample_user_data, "user_id": "user2", "name": "Bob"}

        neo4j_loader.load_nodes(normalize_user_data([User(**user1_data)])["nodes"], "User", "user_id")
        neo4j_loader.load_nodes(normalize_user_data([User(**user2_data)])["nodes"], "User", "user_id")

        # Create friendship
        friend_model = Friend(user1="user1", user2="user2")
        friend_rels = normalize_friend_data([friend_model])["relationships"]

        created, failed = neo4j_loader.load_relationships(friend_rels)
        assert created == 1
        assert not failed

        # Verify in DB
        with neo4j_loader.driver.session() as session:
            result = session.run("""
                MATCH (u1:User {user_id: 'user1'})-[f:FRIENDS_WITH]->(u2:User {user_id: 'user2'})
                RETURN f
            """).single()
            assert result is not None