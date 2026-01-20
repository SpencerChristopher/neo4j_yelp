# Phased Plan to Implement Features

This document outlines an incremental and phased approach for implementing the ETL process and extended data exploration strategy for the Neo4j Yelp Data Project. Each task is designed to deliver value efficiently, with clear objectives and success criteria.

---

## Phase 1: Foundational Setup & Core Business/User ETL

**Objective:** Establish the project environment, secure Neo4j access, create foundational data structures, and load primary `Business` and `User` data. This phase delivers a basic, functional graph of core entities.

### Task 1.1: Project Setup and Core Dependencies
*   **Problem statement:** Establish the basic project structure, virtual environment, and install core Python dependencies for ETL and EDA.
*   **Git branch:** `feat/project-setup`
*   **Success:** `poetry install` completes successfully. `pyproject.toml` explicitly lists `pandas`, `pydantic`, `neo4j` driver, `tqdm`, `scikit-learn`, `difflib` (or similar text processing libraries), and `collections-extended` (or similar for deque if needed).

### Task 1.2: Docker Compose for Neo4j Environment Configuration
*   **Problem statement:** Need a consistent, containerized Neo4j environment with correct volume mounts, memory configuration, and explicit plugin support (APOC, GDS).
*   **Git branch:** `feat/docker-neo4j-setup`
*   **Success:** `docker-compose up -d neo4j` starts successfully. Neo4j Browser is accessible. The `Data/` directory is correctly mounted as `/var/lib/neo4j/import:ro`. Neo4j's heap memory is configured. APOC and GDS plugins are verified as available (e.g., via `CALL dbms.functions()` or `CALL dbms.procedures()` in Cypher).

### Task 1.3: Secure ELT User & Neo4j Index/Constraint Setup
*   **Problem statement:** Neo4j requires a dedicated ETL user with appropriate, minimal write privileges. All necessary unique constraints and indexes must be created for performance and data integrity before data loading. The ELT user's password must be handled securely via environment variables.
*   **Git branch:** `feat/neo4j-security-indexes`
*   **Success:**
    1.  A Python script successfully creates the `elt_user` (if not exists) and grants required `publisher` role privileges (verified by attempting login with `elt_user` and checking roles).
    2.  The password for `elt_user` is sourced securely from an environment variable (e.g., `NEO4J_ELT_PASSWORD`).
    3.  All specified unique constraints and indexes (`Business`, `User`, `City`, `State`, `Category`, `Review`) are successfully created and active in Neo4j (verified via `SHOW CONSTRAINTS` and `SHOW INDEXES` in Cypher).

### Task 1.4: Pydantic Model for `Business` Data
*   **Problem statement:** Develop a Pydantic model to validate and transform `business_small.csv` data, including casing standardization, `point` type creation, and handling optional `postal_code`.
*   **Git branch:** `feat/pydantic-business-model`
*   **Success:** The Pydantic model successfully validates sample `business_small.csv` rows. `city` is converted to Title Case, `state` to Upper Case. `latitude` and `longitude` are combined into a Neo4j `point` object. `postalCode` correctly handles `None` for missing values. Pydantic validation errors for invalid data are logged.

### Task 1.5: ETL for `Business` Nodes, `City`, `State` & Relationships
*   **Problem statement:** Implement the ETL logic to load `business_small.csv` into Neo4j, creating `Business`, `City`, `State` nodes and `LOCATED_IN`, `IN_STATE` relationships, using the Pydantic model.
*   **Git branch:** `feat/load-business-data`
*   **Success:** The `populate_db.py` script runs successfully for `business_small.csv`. Neo4j contains `Business` nodes (count matches CSV rows), `City` nodes, `State` nodes, and `LOCATED_IN`, `IN_STATE` relationships (verified via Cypher counts and sample queries). The `elt_process.log` shows correct handling of `postal_code` nulls and other validation errors.

### Task 1.6: Pydantic Model for `User` Data
*   **Problem statement:** Develop a Pydantic model to validate and transform `user_small.csv` data, including date parsing for `yelping_since` and implicitly dropping irrelevant columns (`Unnamed:*`, `Column1`). The `elite` property is explicitly excluded.
*   **Git branch:** `feat/pydantic-user-model`
*   **Success:** The Pydantic model successfully validates sample `user_small.csv` rows. `yelping_since` is parsed to a `datetime` object with error fallback. `Unnamed:*` and `Column1` are excluded from the model. The `elite` property is not included in the model.

### Task 1.7: ETL for `User` Nodes
*   **Problem statement:** Implement the ETL logic to load `user_small.csv` into Neo4j, creating `User` nodes with their properties, using the Pydantic model.
*   **Git branch:** `feat/load-user-data`
*   **Success:** The `populate_db.py` script runs successfully for `user_small.csv`. Neo4j contains `User` nodes (count matches CSV rows) with correct properties (verified via Cypher counts and sample queries). The `elt_process.log` shows expected handling of `yelping_since` parsing failures.

---

## Phase 2: Core Relationships & Data Quality Refinement

**Objective:** Implement the extended EDA for category normalization, apply it during ETL, and load `Review` data, creating its associated relationships. This phase significantly enhances the graph's utility with key relational data and improved data quality.

### Task 2.1: Extended EDA for `category` Normalization
*   **Problem statement:** Analyze `business_categories_small.csv` to understand category inconsistencies and generate an initial normalization map, leveraging dynamic discovery techniques.
*   **Git branch:** `feat/eda-category-normalization`
*   **Success:** The updated EDA script (`2v_exploratory_data_analysis.py`) processes `business_categories_small.csv`. `category_unique_counts.csv` is generated. A `category_normalization_map.json` is drafted, potentially pre-populated by fuzzy matching/clustering suggestions. The script logs samples of problematic/inconsistent categories.

### Task 2.2: Pydantic Model/Validator for `Category` Normalization
*   **Problem statement:** Integrate the curated `category_normalization_map.json` into a Pydantic model or validator to standardize category names during ETL.
*   **Git branch:** `feat/pydantic-category-norm`
*   **Success:** The Pydantic model/validator successfully applies the `category_normalization_map.json` to sample `business_categories_small.csv` data, ensuring `category` values are consistently standardized (verified by processing samples and inspecting output). Unmappable categories are handled (e.g., logged or assigned a default).

### Task 2.3: ETL for `Category` Nodes & `IN_CATEGORY` Relationships
*   **Problem statement:** Implement the ETL logic to load `business_categories_small.csv` into Neo4j, creating `Category` nodes with normalized names and `IN_CATEGORY` relationships, ensuring all `Business` nodes have their categories linked.
*   **Git branch:** `feat/load-category-data`
*   **Success:** The `populate_db.py` script runs successfully for `business_categories_small.csv`. Neo4j contains `Category` nodes with normalized names and `IN_CATEGORY` relationships (verified via Cypher counts and `MATCH (b:Business)-[:IN_CATEGORY]->(c:Category) RETURN c.name, count(*) ORDER BY count(*) DESC`).

### Task 2.4: Pydantic Model for `Review` Data
*   **Problem statement:** Develop a Pydantic model to validate and transform `review_small.csv` data, specifically parsing the `date` field and explicitly omitting the `text` property as per current dataset scope.
*   **Git branch:** `feat/pydantic-review-model`
*   **Success:** The Pydantic model successfully validates sample `review_small.csv` rows. The `date` field is parsed to a `datetime` object. The `text` property is not expected in the model.

### Task 2.5: ETL for `Review` Nodes, `WROTE`, `REVIEWS` Relationships
*   **Problem statement:** Implement the ETL logic to load `review_small.csv` into Neo4j, creating `Review` nodes and the `WROTE` and `REVIEWS` relationships to connect `User` and `Business` nodes.
*   **Git branch:** `feat/load-review-data`
*   **Success:** The `populate_db.py` script runs successfully for `review_small.csv`. Neo4j contains `Review` nodes (count matches CSV rows), `WROTE` relationships (`User` to `Review`), and `REVIEWS` relationships (`Review` to `Business`) with correct properties (verified via Cypher counts and sample queries). The `elt_process.log` shows expected handling of `date` parsing failures.

---

## Phase 3: Large-Scale Relationships & Final Integration

**Objective:** Integrate the large `user_friendship` import, ensure comprehensive logging, and consolidate all ETL components into a cohesive, production-ready script.

### Task 3.1: Orchestration of `user_friendship.csv` Import
*   **Problem statement:** Implement the Python logic to execute the APOC `apoc.periodic.iterate` command for the large `user_friendship.csv` file from within the ETL script, ensuring robust execution and logging.
*   **Git branch:** `feat/load-friendship-data`
*   **Success:** The `populate_db.py` script successfully orchestrates the APOC call for `user_friendship.csv`. Neo4j contains `User`-[:FRIENDS]->`User` relationships (verified via Cypher counts and `MATCH ()-[:FRIENDS]-() RETURN count(DISTINCT TYPE)`). The `elt_process.log` captures output and errors from the APOC call.

### Task 3.2: Refine and Consolidate Error Reporting & Logging
*   **Problem statement:** Ensure `elt_process.log` captures all necessary details for problematic rows (samples, counts) and provides a clear, comprehensive status of the overall ETL execution, aligning with the `Refined Strategy` document.
*   **Git branch:** `feat/logging-refinement`
*   **Success:** The `elt_process.log` contains structured details for all encountered problems (including filename, row number, column, value, reason). Overall ETL success/failure status is clearly reported. `problematic_rows_*.csv` files are generated for specific high-frequency issues if applicable.

### Task 3.3: Final ETL Script Integration & Orchestration
*   **Problem statement:** Combine all individual ETL steps (Business, User, Category, Review, Friendship) into a single, orchestrated `populate_db.py` script that runs sequentially and handles dependencies correctly, ensuring end-to-end data flow.
*   **Git branch:** `feat/integrate-full-etl`
*   **Success:** A single `populate_db.py` script executes successfully from start to finish, importing all CSV files in the correct, dependent order and handling errors as specified. Neo4j contains all expected nodes and relationships with clean, validated data. The `elt_process.log` provides a complete record of the entire ETL process.

---