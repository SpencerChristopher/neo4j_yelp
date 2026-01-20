# Refined Strategy for Problematic Rows & Normalization Data Exploration

This document outlines an extended Exploratory Data Analysis (EDA) strategy focusing on identifying and preparing "high-risk" data for cleaning and normalization, particularly in scenarios involving large input files. The strategy emphasizes memory efficiency, targeted exploration, and phased understanding of the data.

## 1. Addressing Problematic Rows: A Memory-Efficient Approach

When dealing with large datasets, storing entire DataFrames of problematic rows in memory is often unfeasible. The strategy is to **summarize and sample** problems rather than retaining all problematic data.

*   **Avoid Full Problematic DataFrames in Memory:** Instead of collecting complete problematic rows into a DataFrame, process data in chunks.
*   **Detailed Error Logging:** For each identified problematic record, log comprehensive details to a structured log file. This log entry should include:
    *   `file_name`: The source CSV file.
    *   `row_number`: The original row index in the source file.
    *   `column_name`: The specific column where the issue was found.
    *   `original_value`: The value that caused the problem.
    *   `reason_for_problem`: A concise description of the issue (e.g., "invalid date format", "unrecognized category", "missing required value").
*   **Sample Problematic Rows:** Maintain a small, fixed-size in-memory buffer (e.g., using `collections.deque`) to store a representative sample of problematic records. This buffer provides quick access to examples for manual inspection without consuming excessive memory.
*   **Disk Offloading for In-Depth Analysis:** If a specific type of problem is widespread or requires extensive manual review, consider writing these problematic rows (or just the relevant columns) directly to a *separate, dedicated CSV file* (e.g., `{original_file_name}_problematic_categories.csv`). This allows for out-of-memory analysis using standard tools.

## 2. Data Normalization (Categories Example)

For columns requiring standardization, such as `category` names, the goal is to create canonical forms.

*   **Automated/Assisted Rule Generation:**
    *   **Initial Discovery:** Instead of purely manual identification, use automated techniques to *suggest* mappings. This might involve:
        *   **Frequency Analysis:** Prioritize normalizing highly frequent variations.
        *   **Fuzzy Matching:** Use libraries like `difflib` or text similarity metrics (e.g., Levenshtein distance) to identify close matches that could be synonyms (e.g., "fast-food" vs. "fast food").
        *   **Clustering (Text-based):** For very diverse categories, text embedding (e.g., TF-IDF + K-Means) might group similar terms for easier review.
    *   **Human-in-the-Loop:** These automated suggestions should be reviewed and curated by a human expert to finalize the `{'original_category_variant': 'canonical_category_name'}` dictionary.
*   **Persistent Storage of Mappings:** Once the normalization mapping is curated and finalized, save this dictionary to a persistent file format (e.g., JSON, YAML, or a simple CSV lookup table). This file will then be loaded by your Pydantic models during the ETL process to ensure consistent data.

## 3. Key Pandas Tools for Extended EDA

Leverage Pandas' capabilities for efficient, chunk-based analysis:

*   **`chunksize` in `pd.read_csv`:** Already in use, it's fundamental for memory-efficient processing of large files.
*   **`df[column].value_counts()`:** Essential for analyzing categorical column distributions, identifying frequencies of values, and spotting variations.
*   **`df[column].str.lower().str.strip()`:** For initial standardization of string data (e.g., converting to lowercase and removing leading/trailing whitespace).
*   **`df[column].apply(your_normalization_function)`:** Apply custom Python functions (e.g., a function using your category mapping dictionary) to transform column values.
*   **`difflib.get_close_matches` / Text Similarity Libraries:** For fuzzy matching and suggesting category merges.
*   **Clustering Algorithms (e.g., `sklearn.cluster`):** Potentially for grouping similar text entries to aid in normalization map creation.
*   **`pd.to_datetime(series, errors='coerce', format=...)`:** Critical for date parsing. `errors='coerce'` will convert unparseable dates into `NaT` (Not a Time), which can then be easily identified and handled (`df[col].isnull()`).
*   **`df.loc[condition]`:** For selecting specific rows that meet certain criteria (e.g., problematic rows, rows with `NaT` values).
*   **`df.isnull().sum()`:** To get counts of missing values per column (already in use).
*   **Custom Row Validation:** Integrate a function like `df.apply(lambda row: check_row_for_problems(row), axis=1)` to perform row-wise checks and return a list of identified issues.

## 4. Sensible In-Memory Storage & Logging

*   **In-Memory Storage (for summarization):**
    *   **Problem Counts:** A dictionary (e.g., `problem_summary = {'file_name': {'error_type_1': count, 'error_type_2': count}}`) to keep a running tally of different problem types encountered per file.
    *   **Problem Samples:** `collections.deque` objects (one per file) to store a limited number of *representative* problematic entries (e.g., 100).
    *   **Category Candidates:** A `set` to collect all unique category strings during initial exploration, facilitating the creation of normalization maps.
*   **Logging to File (for persistence and detail):**
    *   **Enhanced Structured Logs:** Utilize Python's `logging` module to output detailed, structured messages (e.g., JSON format) for each problematic row. This enables easier parsing and analysis of logs later.
    *   **Direct Problematic Row Export:** For types of problems requiring extensive review, write the relevant subsets of data directly to dedicated CSV files from within the chunk processing loop. This avoids accumulating large data structures in memory.

## 5. Phased Approach to Data Understanding

A layered approach builds understanding systematically and efficiently:

*   **Phase 0: Initial Overview (Current EDA Script Functionality):**
    *   **Goal:** Obtain a quick, high-level understanding of dataset shape, column names, overall null coverage, and a sample of raw data.
    *   **Tools:** Basic `pd.read_csv` with `chunksize`, `df.isnull().sum()`, `df.head()`, `df.info()`.
    *   **Output:** `eda_log.log` with basic statistics and sample rows.

*   **Phase 1: Targeted Data Quality Assessment (Extended EDA Functionality & Dynamic Discovery):**
    *   **Goal:** Deep dive into "high-risk" columns (e.g., `category`, date fields, potentially `postal_code`) to quantify and characterize specific quality issues, leveraging automated pattern discovery.
    *   **Tools:** `df[col].value_counts()`, `df[col].str` methods, `pd.to_datetime(errors='coerce')`, custom validation functions, `collections.deque` for samples, fuzzy matching/clustering algorithms for rule suggestion.
    *   **Output:**
        *   Detailed logs of specific problems (`eda_quality_report.log`).
        *   Frequency lists/CSVs for unique categories.
        *   Small sample CSVs for manual inspection of complex problematic rows.
        *   A draft of the `category_normalization_map.json` (potentially pre-populated by automated suggestions).

*   **Phase 2: Define Cleaning & Validation Rules:**
    *   **Goal:** Translate the insights from Phase 1 into concrete, executable cleaning and validation logic.
    *   **Tools:** Python functions, regular expressions, lookup dictionaries.
    *   **Output:** Pydantic models with `@field_validator` implementations.

*   **Phase 3: Pre-ETL Validation (on Samples):**
    *   **Goal:** Test the developed Pydantic models and cleaning logic on a representative subset of the raw data before full-scale ETL.
    *   **Tools:** Pydantic models applied to data chunks.
    *   **Output:** Verification of transformed data, review of validation error logs from Pydantic.

*   **Phase 4: Full-Scale ETL with Enhanced Logging & Anomaly Detection:**
    *   **Goal:** Execute the complete ETL process using the refined Pydantic models, with active monitoring for new anomalies.
    *   **Tools:** Pydantic models, Neo4j Python Driver, enhanced logging with structured error details.
    *   **Output:** Populated Neo4j database, `elt_process.log` with detailed success/failure, error reports, and flagged *new* anomalies. This logging can feed into an alerting system.

*   **Phase 5: Post-ETL Verification & Refinement:**
    *   **Goal:** Verify the integrity and quality of the data once loaded into Neo4j.
    *   **Tools:** Cypher queries (e.g., checking for unexpected `NULL`s, unnormalized values, missing relationships), Neo4j Browser.
    *   **Output:** Confirmation of data quality or identification of minor issues requiring further ETL refinement.
