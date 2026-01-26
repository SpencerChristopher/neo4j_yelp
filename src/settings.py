# This file will centralize configuration management for the ETL pipeline,
# such as file paths, batch sizes, and Neo4j connection details.
from dotenv import load_dotenv
import os

load_dotenv()

# Neo4j Credentials
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")


# Data File Paths
DATA_DIR = "Data"
BUSINESS_CSV = 'business_small.csv'
BUSINESS_CITY_CSV = 'business_city.csv' # Consider if this is the category source
REVIEW_CSV = 'review_small.csv'
USER_CSV = 'user_small.csv'
CATEGORY_CSV = 'business_categories_small.csv' # Corrected from EDA log
FRIEND_CSV = 'user_friendship.csv' # Corrected from EDA log

# ETL Configuration
BATCH_SIZE = 1000
LOG_FILE = "logs/elt_process.log"
DEAD_LETTER_FILE = "logs/dead_letters.jsonl"
