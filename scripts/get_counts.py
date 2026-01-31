import pandas as pd
import os
from pathlib import Path

# Get the directory of the current script
script_dir = Path(__file__).parent
# Construct the path to the 'tests/data' directory relative to the script
test_data_path = script_dir.parent / "tests" / "data"

business_csv = test_data_path / "test.business_small.csv" # Use Path objects for joining

# Read only the first chunk (BATCH_SIZE = 1000)
df_business = pd.read_csv(business_csv, chunksize=1000).get_chunk()

unique_states = df_business['state'].nunique()
unique_cities = df_business.apply(lambda row: f"{row['city']}|{row['state']}", axis=1).nunique()
unique_postal_codes = df_business['postal_code'].nunique()

print(f"Unique states in first 1000 business records: {unique_states}")
print(f"Unique cities (city|state) in first 1000 business records: {unique_cities}")
print(f"Unique postal codes in first 1000 business records: {unique_postal_codes}")

category_csv = test_data_path / "test.business_categories_small.csv" # Use Path objects
df_categories = pd.read_csv(category_csv, chunksize=1000).get_chunk()
unique_categories = df_categories['category'].nunique()

print(f"Unique categories in first 1000 category records: {unique_categories}")

# --- New section for friendship counts ---
friend_csv = test_data_path / "test.user_friendship.csv" # Use Path objects
try:
    with open(friend_csv, 'r') as f:
        # Read all lines and subtract 1 for the header
        friend_lines = sum(1 for line in f) - 1
    print(f"Number of friendship records in test.user_friendship.csv: {friend_lines}")
except FileNotFoundError:
    print(f"test.user_friendship.csv not found at {friend_csv}")
    friend_lines = 0
# --- End new section ---