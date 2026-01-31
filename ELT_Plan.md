### **ETL Specification for Neo4j Import**

#### **Overall Strategy & Optimizations**

*   **Pydantic for Data Validation & Transformation:** All incoming data will be validated and transformed using Pydantic models before being sent to Neo4j. This ensures data quality, type correctness, and handles transformations like date parsing, geo-point creation, and casing standardization. Pydantic's rich error reporting will be used for detailed logging of data quality issues.
*   **Chunking & In-Memory Batching:** CSV files will be read in chunks. These chunks will be processed (validated, transformed by Pydantic) and then aggregated into in-memory batches for efficient transmission to Neo4j. No external caching tools (like Redis) will be used; memory management will be handled by Python's standard capabilities.
*   **Transactional Batch Processing:** Data will be sent to Neo4j in carefully sized batches, with each batch constituting a single transaction. This ensures atomicity (all or nothing) and provides explicit feedback from Neo4j for each batch.
*   **Robust Error Handling & Logging:** Each batch transaction will include `try-except` blocks to catch Neo4j and Pydantic-related errors. Detailed logging will capture batch success/failure, number of records processed, and any specific data quality issues, written to a dedicated `elt_process.log`.
*   **Minimal Tooling:** The entire ELT process will be orchestrated using standard Python libraries (Pandas, Pydantic, Neo4j Driver/Py2neo) without additional external orchestration tools.
*   **Community Edition Plugins:** Only free-to-use, Community Edition compatible APOC and GDS plugins will be used.

### **High-Risk Columns & Targeted Exploration for ELT Cleaning**

To ensure data quality and effective graph modeling, targeted exploratory data analysis will be performed on specific "high-risk" columns identified during initial profiling. This exploration will directly inform Pydantic validation and transformation rules.

*   **`business_categories_small.csv` - `category`**:
    *   **Risk**: Semantic inconsistencies, variations in phrasing, and overly granular/redundant entries (e.g., "burger fries", "fast food", "milk shake").
    *   **Exploration**:
        1.  Analyze unique category names and their frequencies.
        2.  Identify common synonyms, sub-categories that can be merged, and terms to exclude.
    *   **ELT Action**: Implement Pydantic validators to:
        1.  Standardize casing and terminology.
        2.  Map variations to canonical category names (e.g., using a lookup dictionary).
        3.  Filter out or combine "useless" or overly granular categories.

*   **`review_small.csv` - `date` & `user_small.csv` - `yelping_since`**:
    *   **Risk**: Date/time formats can be inconsistent, leading to parsing errors.
    *   **Exploration**:
        1.  Sample these columns to identify any variations in date/time string formats beyond the primary expected format (`DD/MM/YYYY HH:MM`).
    *   **ELT Action**: Enhance Pydantic `datetime` validators to robustly handle anticipated format variations, with clear logging for unparseable dates.

### **Neo4j Index and Constraint Creation**

To ensure optimal query performance and data integrity, unique constraints and indexes will be created on key node properties *before* the main data import begins. These are crucial for efficient `MERGE` and `MATCH` operations.

*   **Action**: The ETL script will execute the following Cypher commands:
    ```cypher
    CREATE CONSTRAINT FOR (b:Business) REQUIRE b.id IS UNIQUE;
    CREATE CONSTRAINT FOR (u:User) REQUIRE u.id IS UNIQUE;
    CREATE CONSTRAINT FOR (c:City) REQUIRE c.name IS UNIQUE;
    CREATE CONSTRAINT FOR (s:State) REQUIRE s.code IS UNIQUE;
    CREATE CONSTRAINT FOR (cat:Category) REQUIRE cat.name IS UNIQUE;
    CREATE CONSTRAINT FOR (r:Review) REQUIRE r.id IS UNIQUE; // Crucial for Review nodes
    ```

#### **Neo4j Container Preparation (Docker)**

To ensure the Neo4j instance is prepared for the population, the `docker-compose.yml` will need the following modifications:

*   **Volume Mount for `/import`:** The local `Data` directory containing the CSV files must be mounted into the Neo4j container's `/var/lib/neo4j/import` directory. This allows Cypher's `LOAD CSV` and APOC's `apoc.load.csv` to access the files directly and efficiently.
    ```yaml
    services:
      neo4j:
        # ... existing config ...
        volumes:
          - ./Data:/var/lib/neo4j/import:ro # Read-only mount for data safety
        # ...
    ```
*   **Memory Configuration:** Adjust Neo4j's heap memory settings to optimize for large imports, especially when using APOC. These are set via environment variables.
    ```yaml
    services:
      neo4j:
        # ... existing config ...
        environment:
          - NEO4J_dbms_memory_heap_initial__size=2G # Example: Adjust based on available RAM
          - NEO4J_dbms_memory_heap_max__size=4G    # Example: Adjust based on available RAM
          - NEO4J_apoc_import_file_enabled=true    # Enable APOC for file imports
          - NEO4J_apoc_export_file_enabled=true    # (Optional, for future use)
        # ...
    ```

*   **Plugin Verification:** Ensure the `docker-compose.yml` correctly references a Community Edition compatible Neo4j image that includes the necessary APOC and GDS plugins.

#### **1. Source File: `business_small.csv`**
*   **Data We're Taking:**
    | CSV Column | Neo4j Target | Transformation / Data Type | Pydantic Handling |
    | :--- | :--- | :--- | :--- |
    | `business_id`| `(:Business {id})` | String, Unique Key | `str` |
    | `name` | `(:Business {name})` | String | `str` |
    | `city` | `(:City {name})` | String, Title Case | `str` with `validator` for title case |
    | `state` | `(:State {code})` | String, Upper Case | `str` with `validator` for upper case |
    | `postal_code`| `(:Business {postalCode})` | String | `Optional[str]` |
    | `latitude`, `longitude` | `(:Business {location})` | Neo4j `point` type | Combined and validated by Pydantic `validator` |
    | `stars` | `(:Business {stars})` | Float | `float` |
    | `review_count`| `(:Business {reviewCount})` | Integer | `int` |
    | `is_open` | `(:Business {isOpen})` | Boolean | `bool` (converted from int 0/1) |
*   **Merge Plan:** This file creates the primary `Business` nodes, and associated `City` and `State` nodes and relationships.
    ```cypher
    // For each row in business_small.csv processed by Pydantic
    UNWIND $rows AS row
    MERGE (b:Business {id: row.business_id})
    SET b.name = row.name,
        b.stars = row.stars,
        b.reviewCount = row.review_count,
        b.isOpen = row.is_open,
        b.location = point({latitude: row.latitude, longitude: row.longitude}),
        b.postalCode = row.postal_code

    MERGE (c:City {name: row.city})
    MERGE (s:State {code: row.state})
    MERGE (b)-[:LOCATED_IN]->(c)
    MERGE (c)-[:IN_STATE]->(s)
    ```
*   **Bad Data Plan:** `postal_code` missing values will be handled by `Optional[str]` in Pydantic. Pydantic validation errors for other fields will be logged to `elt_process.log`.

#### **2. Source File: `user_small.csv`**
*   **Data We're Taking:**
    | CSV Column | Neo4j Target | Transformation / Data Type | Pydantic Handling |
    | :--- | :--- | :--- | :--- |
    | `user_id` | `(:User {id})` | String, Unique Key | `str` |
    | `name` | `(:User {name})` | String | `str` |
    | `review_count`| `(:User {reviewCount})`| Integer | `int` |
    | `yelping_since`| `(:User {yelpingSince})`| Neo4j `datetime` | `datetime` (parsed from string, with error fallback) |
    | `useful`, `funny`, `cool`, `fans` | User properties | Integer | `int` |
    | `average_stars`| `(:User {averageStars})`| Float | `float` |
    | `compliment_*`| User properties | Integer | `int` |
    | **Note:** The `elite` property listed in `project_outline.md` is not present in `user_small.csv` and will not be imported in this phase.
    | `Column1`, `Unnamed:*` | (Dropped) | (Dropped) | Not included in Pydantic model |
*   **Merge Plan:** This file creates the primary `User` nodes.
    ```cypher
    // For each row in user_small.csv processed by Pydantic
    UNWIND $rows AS row
    MERGE (u:User {id: row.user_id})
    SET u.name = row.name,
        u.reviewCount = row.review_count,
        // ... set all other properties from Pydantic model ...
        u.yelpingSince = row.yelping_since // Pydantic already converted to datetime object
    ```
*   **Bad Data Plan:**
    *   `yelping_since`: Pydantic `validator` will attempt parsing to `datetime`. On failure, it will log the error and set to `None`.
    *   `Unnamed:*` and `Column1`: These columns will be implicitly dropped by not including them in the Pydantic model definition. Pydantic will ensure only valid columns are processed.

#### **3. Source File: `review_small.csv`**
*   **Data We're Taking:** All columns, after validation and transformation. This file links existing `User` and `Business` nodes.
*   **Merge Plan:** This creates the `:REVIEWED` relationship. **This must run after `business_small.csv` and `user_small.csv` are fully imported.**
    ```cypher
    // For each row in review_small.csv processed by Pydantic
    UNWIND $rows AS row
    MATCH (u:User {id: row.user_id})
    MATCH (b:Business {id: row.business_id})
    // Create or MERGE the Review node as per project_outline.md
    MERGE (rev:Review {id: row.review_id})
    ON CREATE SET
        rev.stars = row.stars,
        rev.useful = row.useful,
        rev.funny = row.funny,
        rev.cool = row.cool,
        rev.date = row.date // Pydantic already converted to datetime object
        // NOTE: 'text' property is in project_outline.md but not in review_small.csv, and is therefore not loaded in this phase.
    // Create relationships to the Review node
    MERGE (u)-[:WROTE]->(rev)
    MERGE (rev)-[:REVIEWS]->(b)
    ```
*   **Bad Data Plan:** `date`: Pydantic `validator` will attempt parsing. On failure, log the error and set to `None`.

#### **4. Source File: `business_categories_small.csv`**
*   **Data We're Taking:** All columns, after validation. Links existing `Business` nodes to `Category` nodes.
*   **Merge Plan:** **Must run after `business_small.csv` is imported.**
    ```cypher
    // For each row in business_categories_small.csv processed by Pydantic
    UNWIND $rows AS row
    MATCH (b:Business {id: row.business_id})
    MERGE (c:Category {name: row.category})
    MERGE (b)-[:IN_CATEGORY]->(c)
    ```
*   **Bad Data Plan:** Data is expected to be clean. Pydantic will still validate.

#### **5. Source File: `user_friendship.csv`**
*   **Data We're Taking:** All columns, after validation. Links existing `User` nodes.
*   **Merge Plan:** **Must run after `user_small.csv` is fully imported.** Due to its massive size (37M rows), it will use APOC's `apoc.periodic.iterate` for efficient, batched processing within Neo4j.
    *   **Orchestration**: The Python ETL script will execute this `apoc.periodic.iterate` call directly via the Neo4j Python driver.
    ```cypher
    CALL apoc.periodic.iterate(
        "LOAD CSV WITH HEADERS FROM 'file:///user_friendship.csv' AS row RETURN row",
        "MATCH (u1:User {user_id: row.user1}) " +
        "MATCH (u2:User {user_id: row.user2}) " +
        "MERGE (u1)-[:FRIENDS_WITH]->(u2)",
        {batchSize: 10000, parallel: true, iterateList: true, retries: 5}
    ) YIELD batches, total, errorMessages
    RETURN batches, total, errorMessages
    ```
*   **Bad Data Plan:** Data is expected to be clean. APOC's `LOAD CSV` handles basic type conversions; any issues will be logged by Neo4j itself.

---
### Summary of Columns Requiring Special Handling (Pydantic-Managed)

*   **Dates to Parse:** `review_small.csv.date`, `user_small.csv.yelping_since`.
*   **Columns to Drop:** `user_small.csv.Unnamed: 21`, `user_small.csv.Unnamed: 22`, `user_small.csv.Unnamed: 23`, `user_small.csv.Column1`.
*   **Values to Standardize:** `business_small.csv.city` (Title Case), `business_small.csv.state` (Upper Case).
*   **Columns to Combine:** `business_small.csv.latitude`, `business_small.csv.longitude` into a Neo4j `point`.