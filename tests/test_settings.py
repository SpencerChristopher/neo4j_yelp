import pytest
import os
import tempfile
from pathlib import Path
from src.settings import Settings, settings as global_settings

@pytest.fixture(autouse=True)
def clean_env():
    """Fixture to clear relevant environment variables before each test."""
    original_env = os.environ.copy()
    keys_to_clear = [
        "NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD",
        "DATA_DIR", "BUSINESS_CSV", "REVIEW_CSV", "USER_CSV",
        "CATEGORY_CSV", "FRIEND_CSV", "BATCH_SIZE",
        "LOG_FILE", "DEAD_LETTER_FILE"
    ]
    for key in keys_to_clear:
        if key in os.environ:
            del os.environ[key]
    # Ensure NEO4J_PASSWORD is explicitly cleared even if set by external .env
    if "NEO4J_PASSWORD" in os.environ:
        del os.environ["NEO4J_PASSWORD"]
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def temp_env_file():
    """Fixture to create a temporary .env file for testing."""
    fd, path = tempfile.mkstemp(suffix=".env")
    yield Path(path)
    os.close(fd)
    os.unlink(path)


def test_default_settings():
    """Test that default values are loaded when no .env or env vars are present."""
    s = Settings(_env_file=None)
    assert s.NEO4J_URI == "bolt://localhost:7687"
    assert s.NEO4J_USER == "neo4j"
    assert s.NEO4J_PASSWORD is None
    assert s.DATA_DIR == Path("Data")
    assert s.BATCH_SIZE == 1000
    assert s.LOG_FILE == Path("logs/elt_process.log")
    assert s.DEAD_LETTER_FILE == Path("logs/dead_letters.jsonl")


def test_env_file_loading(temp_env_file):
    """Test that settings are loaded correctly from a .env file."""
    env_content = """
NEO4J_URI=bolt://envfile:7687
NEO4J_USER=envuser
NEO4J_PASSWORD=envpass
BATCH_SIZE=2000
DATA_DIR=EnvData
LOG_FILE=logs/env_log.log
"""
    temp_env_file.write_text(env_content)

    # Force reload of settings with the temporary .env file
    s = Settings(_env_file=temp_env_file)

    assert s.NEO4J_URI == "bolt://envfile:7687"
    assert s.NEO4J_USER == "envuser"
    assert s.NEO4J_PASSWORD == "envpass"
    assert s.BATCH_SIZE == 2000
    assert s.DATA_DIR == Path("EnvData")
    assert s.LOG_FILE == Path("logs/env_log.log")
    # Check default for a variable not in .env
    assert s.BUSINESS_CSV == Path("business_small.csv")


def test_environment_variable_precedence(temp_env_file):
    """Test that environment variables take precedence over .env file values."""
    env_content = """
NEO4J_URI=bolt://envfile:7687
NEO4J_USER=envuser
BATCH_SIZE=2000
"""
    temp_env_file.write_text(env_content)

    os.environ["NEO4J_URI"] = "bolt://envvar:7687"
    os.environ["BATCH_SIZE"] = "3000"

    s = Settings(_env_file=temp_env_file)

    assert s.NEO4J_URI == "bolt://envvar:7687"
    assert s.NEO4J_USER == "envuser"  # From .env, as not overridden by env var
    assert s.BATCH_SIZE == 3000

    # Removed global_settings assertion as it would not reflect changes made within a test after initial import.


def test_path_types():
    """Test that Path fields are correctly parsed."""
    s = Settings()
    assert isinstance(s.DATA_DIR, Path)
    assert s.DATA_DIR == Path("Data")
    assert isinstance(s.LOG_FILE, Path)
    assert isinstance(s.BUSINESS_CSV, Path)

    os.environ["DATA_DIR"] = "/tmp/my_data"
    s_env = Settings()
    assert s_env.DATA_DIR == Path("/tmp/my_data")

