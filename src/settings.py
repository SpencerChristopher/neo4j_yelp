# This file will centralize configuration management for the ETL pipeline,
# such as file paths, batch sizes, and Neo4j connection details.
from dotenv import load_dotenv
import os

load_dotenv()

# Neo4j Credentials
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_ELT_USER = os.getenv("NEO4J_ELT_USER", "elt_user")
NEO4J_ELT_PASSWORD = os.getenv("NEO4J_ELT_PASSWORD")

# Data File Paths
DATA_DIR = "Data"
BUSINESS_CSV = os.path.join(DATA_DIR, 'business_small.csv')
REVIEW_CSV = os.path.join(DATA_DIR, 'review_small.csv')
USER_CSV = os.path.join(DATA_DIR, 'user_small.csv')

# ETL Configuration
BATCH_SIZE = 1000
LOG_FILE = "logs/elt_process.log"
DEAD_LETTER_FILE = "logs/dead_letters.jsonl"
