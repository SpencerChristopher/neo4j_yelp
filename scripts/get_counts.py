import pandas as pd
import os

test_data_path = "../tests/data"
business_csv = os.path.join(test_data_path, "test.business_small.csv")

# Read only the first chunk (BATCH_SIZE = 1000)
df_business = pd.read_csv(business_csv, chunksize=1000).get_chunk()

unique_states = df_business['state'].nunique()
unique_cities = df_business.apply(lambda row: f"{row['city']}|{row['state']}", axis=1).nunique()
unique_postal_codes = df_business['postal_code'].nunique()

print(f"Unique states in first 1000 business records: {unique_states}")
print(f"Unique cities (city|state) in first 1000 business records: {unique_cities}")
print(f"Unique postal codes in first 1000 business records: {unique_postal_codes}")

category_csv = os.path.join(test_data_path, "test.business_categories_small.csv")
df_categories = pd.read_csv(category_csv, chunksize=1000).get_chunk()
unique_categories = df_categories['category'].nunique()

print(f"Unique categories in first 1000 category records: {unique_categories}")