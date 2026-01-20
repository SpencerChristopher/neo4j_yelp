# Project Implementation Reference Guide

This document serves as a comprehensive guide, mapping each phase and key tasks within the `Phased_plan.md` to the foundational project documents (`ELT_Plan.md`, `project_outline.md`, `Refined Strategy for Problematic_Rows_&_Normalization_Data_Exploration.md`) that inform its objectives, methodologies, and specific implementation details.

---

## **Phase 1: Foundational Setup & Core Business/User ETL**

This phase focuses on establishing the core environment and loading the primary node types.

*   **Primary Informing Document:** `ELT_Plan.md`
    *   **Overall Strategy & Optimizations:** Guides the fundamental approach (Pydantic, chunking, transactional processing, error handling, minimal tooling, and plugin strategy).
    *   **Neo4j Container Preparation (Docker):** Directly informs **Task 1.2 (Docker Compose)** for volume mounts, memory config, and plugin verification.
    *   **Dedicated ELT User:** Informs **Task 1.3 (Secure ELT User)** for user creation and privileges, including the updated secure password handling.
    *   **Neo4j Index and Constraint Creation:** Directly informs **Task 1.3 (Neo4j Index/Constraint Setup)** with the specific Cypher commands.
    *   **Source File: `business_small.csv`:** Informs **Task 1.4 (Pydantic Model for Business)** and **Task 1.5 (ETL for Business)** for data mapping, transformations (casing, point), and Cypher merge plans.
    *   **Source File: `user_small.csv`:** Informs **Task 1.6 (Pydantic Model for User)** and **Task 1.7 (ETL for User)** for data mapping, transformations (date parsing, dropped columns), and Cypher merge plans. Also clarifies the abandonment of the `elite` property.
*   **Supporting Document:** `project_outline.md`
    *   **Core Data Model (Nodes & Relationships):** Provides the high-level schema for `Business` and `User` nodes and their properties, guiding **Tasks 1.4-1.7**. (Note: `elite` property has been removed).
*   **Methodology Document:** `Refined Strategy for Problematic_Rows_&_Normalization_Data_Exploration.md`
    *   **Sections 1 & 4 (Addressing Problematic Rows & Sensible In-Memory Storage & Logging):** Provides general guidance on memory-efficient approaches and logging that should be implemented from **Task 1.5** onwards for ETL.

---

## **Phase 2: Core Relationships & Data Quality Refinement**

This phase focuses on loading remaining core entities, implementing crucial data quality improvements, and forming key relationships.

*   **Primary Informing Document:** `ELT_Plan.md`
    *   **High-Risk Columns & Targeted Exploration for ELT Cleaning:** This entire section is critical for **Task 2.1 (Extended EDA for Category)** and **Task 2.4 (Pydantic Model for Review)** (specifically for date parsing).
    *   **Source File: `business_categories_small.csv`:** Informs **Task 2.2 (Pydantic Model/Validator for Category)** and **Task 2.3 (ETL for Category)** on data mapping and Cypher merge plans.
    *   **Source File: `review_small.csv`:** Informs **Task 2.4 (Pydantic Model for Review)** and **Task 2.5 (ETL for Review)** on data mapping, transformations (date parsing), and Cypher merge plans. It also clarifies the absence of the `text` property.
*   **Key Methodology Document:** `Refined Strategy for Problematic_Rows_&_Normalization_Data_Exploration.md` (This document is central to this entire phase).
    *   **Section 1 (Addressing Problematic Rows):** Guides the approach to logging and sampling problematic rows during all ETL tasks.
    *   **Section 2 (Data Normalization - Categories Example):** Provides the methodology for automated/assisted rule generation, human-in-the-loop curation, and persistent storage of mappings, directly informing **Tasks 2.1 & 2.2**.
    *   **Section 3 (Key Pandas Tools for Extended EDA):** Lists specific tools to be used in **Task 2.1**.
    *   **Section 4 (Sensible In-Memory Storage & Logging):** Guides the in-memory storage and logging strategy for problematic rows and category candidates in **Task 2.1**.
    *   **Section 5 (Phased Approach to Data Understanding - Phase 1 & 2):** Provides the detailed steps and goals for **Tasks 2.1 & 2.2**.
*   **Supporting Document:** `project_outline.md`
    *   **Core Data Model (Nodes & Relationships):** Guides the high-level schema for `Category` and `Review` nodes and their relationships (`IN_CATEGORY`, `WROTE`, `REVIEWS`), informing **Tasks 2.3 & 2.5**. (Note: `text` property has been removed for `Review`).
    *   **Sentiment Analysis:** Informs the handling of `stars`, `useful`, `funny`, `cool` metrics within **Task 2.4 & 2.5**.

---

## **Phase 3: Large-Scale Relationships & Final Integration**

This phase completes the graph population and refines the overall ETL process.

*   **Primary Informing Document:** `ELT_Plan.md`
    *   **Source File: `user_friendship.csv`:** Directly informs **Task 3.1 (Orchestration of Friendship Import)** for its use of APOC `apoc.periodic.iterate` and Python orchestration.
*   **Key Methodology Document:** `Refined Strategy for Problematic_Rows_&_Normalization_Data_Exploration.md`
    *   **Section 1 (Addressing Problematic Rows):** Guides the comprehensive logging strategy for problematic rows in **Task 3.2**.
    *   **Section 4 (Sensible In-Memory Storage & Logging):** Provides specific guidance on enhanced structured logs and how to handle problematic rows for **Task 3.2**.
    *   **Section 5 (Phased Approach to Data Understanding - Phase 4 & 5):** Guides the final ETL execution, comprehensive logging, and post-ETL verification activities in **Tasks 3.2 & 3.3**.

---