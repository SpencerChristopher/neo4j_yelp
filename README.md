# Yelp Graph Analyzer

This project aims to build a Yelp-style recommendation engine using Python and Neo4j. It processes Yelp dataset information to create a graph database for efficient querying and analysis.

## Key Features:
- **Comprehensive ETL Strategy:** Detailed plan for data extraction, transformation, and loading into Neo4j, documented in `ELT_Plan.md`.
- **Data Validation with Pydantic:** Utilizes Pydantic models for robust schema validation and data transformation during the ETL process, ensuring data quality.
- **Efficient Data Ingestion:** Implements chunking and batch processing for optimal memory management and performance during Neo4j data loading.
- **Graph Data Model:** Utilizes a detailed graph data model for users, businesses, reviews, categories, and locations.
- **Neo4j Integration:** Integrates with Neo4j using the official Python driver, leveraging Community Edition compatible APOC plugins for advanced functionalities.
- **Docker-based Environment:** A `docker-compose.yml` setup provides a consistent Neo4j environment, pre-configured for ETL optimizations.

## Getting Started

### 1. Clone the Repository & Initialize Git LFS

This repository uses Git Large File Storage (LFS) for handling large CSV data files within the `Data/` directory. Ensure you have Git LFS installed before cloning.

```bash
git lfs install
git clone <repository-url>
cd neo4j_yelp # Or your project root directory
```

### 2. Prepare the Data

The raw CSV data is **not** included directly in the repository due to its large size. You can download the `YelpSmall.zip` file from the [original data source](LINK_TO_DATA_SOURCE_HERE) and extract its contents into the `Data/` directory.

```bash
unzip YelpSmall.zip -d Data/
```
**Note:** The `Data/` directory itself is not tracked by Git (it's in `.gitignore`).

### 3. Set up the Neo4j Environment

The project uses Docker Compose to manage the Neo4j database.
*   Review and configure `docker-compose.yml` as per the `ELT_Plan.md` for optimal ETL performance (e.g., memory settings, volume mounts).
*   Ensure a dedicated ELT user is configured in Neo4j with appropriate permissions for the ETL script.

```bash
docker-compose up -d neo4j
```

### 4. Run the ETL Process

Refer to `ELT_Plan.md` for the detailed strategy. The `populate_db.py` script (to be created) will execute the ETL.

### 5. Further Exploration

The `2v_exploratory_data_analysis.py` script was used for initial data profiling and can be run to regenerate data insights.

```bash
python 2v_exploratory_data_analysis.py
```
