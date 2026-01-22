
## Phase 1: Foundational Setup & Geographic Skeleton

**Objective:** Establish the project environment, enforce data integrity through constraints, and build the "geographic truth" skeleton before loading primary entities.

### Task 1.1: Project Setup and Core Dependencies

* **Status:** **Complete**
* **Problem statement:** Establish basic project structure and virtual environment.
* **Success:** `poetry install` or `pip install` completes with `pydantic`, `neo4j`, `pandas`, and `tqdm`.

### Task 1.2: Docker Compose for Neo4j Environment

* **Status:** **Complete**
* **Problem statement:** Consistent containerized Neo4j environment with APOC and GDS plugins.
* **Success:** Neo4j Browser is accessible; `RETURN gds.version()` confirms plugin availability.

### Task 1.3: Secure Identity & Multi-Layer Constraints

* **Status:** **Updated/Pending**
* **Problem statement:** Enforce identity protection across 7 node types to support recommendation queries and prevent data duplication.
* **Success:** `SHOW CONSTRAINTS` confirms the following are active:
* **Unique Constraints:** `User.user_id`, `Business.business_id`, `Review.review_id`, `Category.name`, `State.code`, `PostalCode.code`.
* **Composite Unique Constraint:** `City(name, state)` (ensures "Springfield, IL" is distinct from "Springfield, MO").



### Task 1.4: DB-Agnostic Pydantic Model for Business Data

* **Status:** **Updated**
* **Problem statement:** Validate `business_small.csv`. Enforce the rule: `State` is mandatory, plus either `City` OR `Postal_Code`. `Postal_Code` must be a 5-digit integer (e.g., 85392). Coordinates must be standardized as floats, agnostic of the database. Address is dropped.
* **Success:**
* Validation fails if `State` is missing.
* Validation fails if *both* `City` and `Postal_Code` are missing.
* `postal_code` is successfully validated and stored as an `int` (501-99950 range).
* `latitude`/`longitude` are preserved as floats for transaction-stage conversion.



### Task 1.5: Skeleton-First ETL (Business & Geography)

* **Status:** **In Progress**
* **Problem statement:** Load geographic truth from `business_city.csv` first to define valid `City` and `State` nodes. Link `Business` nodes to this skeleton via `LOCATED_NEAR` relationships while preserving raw claims as properties.
* **Success:** `MATCH (b:Business)-[:LOCATED_NEAR]->(c:City)` returns verified matches; `postal_code` is stored as an integer in Neo4j.

### Task 1.6: Pydantic Model for User Social Capital

* **Status:** **Complete**
* **Problem statement:** Validate `user_small.csv` while stripping out the `elite` column and any `Unnamed` index columns. Normalize names to Title Case and ensure all 11 compliment categories are non-negative integers.
* **Success:** User nodes are imported without the `elite` property. `yelping_since` is parsed as a valid datetime object for Neo4j temporal storage.

---

## Phase 2: Review, Social, & Taxonomy Ingestion

**Objective:** Connect the "nouns" (User, Business) through "verbs" (Wrote, Of, Friends) and categorize the businesses.

### Task 2.1: Pydantic Model for Reviews & Friendship

* **Status:** **Pending**
* **Problem statement:** Validate `review_small.csv` and `user_friendship.csv`. Standardize review dates and ensure `stars` are validated as integers.
* **Success:** Pydantic model rejects reviews with stars outside the 1–5 range. Friendship rows with missing `user_id` pairs or self-loops are flagged.

### Task 2.2: Interaction & Social Layer Ingestion

* **Status:** **Pending**
* **Problem statement:** Load Reviews and connect `(User)-[:WROTE]->(Review)-[:OF]->(Business)`. Ingest the friendship graph as a symmetric `[:FRIENDS_WITH]` relationship.
* **Success:** The graph supports traversing from a User to their Friends and subsequently to the Businesses those Friends have reviewed.

### Task 2.3: Taxonomy Loading (Categories)

* **Status:** **Pending**
* **Problem statement:** Parse the `categories` string from business data, creating unique `(:Category)` nodes and `[:CLAIMS_CATEGORY]` relationships.
* **Success:** `MATCH (b:Business)-[:CLAIMS_CATEGORY]->(c:Category)` allows for filtering businesses by specific types (e.g., "Italian", "Restaurants").

---

## Phase 3: Recommendation Queries & Success Metrics

**Objective:** Execute and verify the complex queries required for the recommendation engine application.

### Task 3.1: Recommendation Query Implementation

* **Status:** **Pending**
* **Query 2a (Discovery):** List all businesses, their verified city, and their categories.
* **Query 2b (High-Value Content):** Find businesses with `stars >= 4` and reviews tagged `useful >= 40`.
* **Query 2c (Social Recommendation):** Find users who reviewed the same business as their friends or friends-of-friends (Degree 1 or 2).

### Task 3.2: Final ETL Integration & Orchestration

* **Status:** **Pending**
* **Problem statement:** Orchestrate all loaders into a single `populate_db.py` script.
* **Success Metrics:**
* A single script run imports the full dataset in the correct order.
* Query results match the expected output samples for 2a, 2b, and 2c.
* `elt_process.log` provides a clean audit trail of every row processed and every constraint created.