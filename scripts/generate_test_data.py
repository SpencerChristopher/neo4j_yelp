import pandas as pd
import os
import sys

# Add the project root to the sys.path to allow importing settings
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.settings import DATA_DIR, BUSINESS_CSV, REVIEW_CSV, USER_CSV, CATEGORY_CSV, FRIEND_CSV

# Configuration
TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), '../tests/data')
SAMPLE_PERCENTAGE = 0.05  # 5% sample
RANDOM_STATE = 42      # For reproducibility

# Ensure test data directory exists
os.makedirs(TEST_DATA_DIR, exist_ok=True)

csv_files_to_sample = {
    "business": BUSINESS_CSV,
    "review": REVIEW_CSV,
    "user": USER_CSV,
    "friend": FRIEND_CSV,
    "category": CATEGORY_CSV,
}

print(f"Generating sampled data for testing (sample percentage: {SAMPLE_PERCENTAGE * 100}%)...")
print(f"Source data directory: {DATA_DIR}")
print(f"Destination test data directory: {TEST_DATA_DIR}")

for key, filename in csv_files_to_sample.items():
    input_path = os.path.join(DATA_DIR, filename)
    output_filename = f"test.{filename}"
    output_path = os.path.join(TEST_DATA_DIR, output_filename)

    if not os.path.exists(input_path):
        print(f"Warning: Input file not found: {input_path}. Skipping.")
        continue

    print(f"Processing {filename}...")
    try:
        df = pd.read_csv(input_path)
        sampled_df = df.sample(frac=SAMPLE_PERCENTAGE, random_state=RANDOM_STATE)
        sampled_df.to_csv(output_path, index=False)
        print(f"  Generated {output_filename} with {len(sampled_df)} rows.")
    except Exception as e:
        print(f"Error processing {filename}: {e}")

print("Sample data generation complete.")
