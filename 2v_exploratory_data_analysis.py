#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Standalone script for Exploratory Data Analysis (EDA) of Yelp CSV data.
# This script profiles all CSV files in a specified data directory, gathering
# statistics on row counts, data types, and null coverage without loading
# entire files into memory.

import pandas as pd
from io import StringIO
from typing import Dict, Any, Optional
import os
import logging
import sys

# Global logger instance
logger = logging.getLogger(__name__)

def setup_logging() -> None:
    """Configures the root logger for the script."""
    log_file_path = 'eda_log.log'
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    try:
        file_handler = logging.FileHandler(log_file_path, mode='w', encoding='utf-8')
        handlers = [file_handler, logging.StreamHandler(sys.stdout)]
    except Exception as e:
        print(f"Error creating file handler: {e}")
        handlers = [logging.StreamHandler(sys.stdout)]

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    for handler in handlers:
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    
    logger.info("Logging configured.")


def load_and_profile_csv(file_path: str, chunk_size: int = 10000) -> Optional[Dict[str, Any]]:
    """
    Profiles a CSV file by reading it in chunks and returns a dictionary of statistics.
    This version is optimized for memory and does NOT return a DataFrame.
    """
    logger.info(f"--- Starting to profile: {os.path.basename(file_path)} (stats-only) ---")
    if not os.path.exists(file_path):
        logger.error(f"File not found at: {file_path}")
        return None

    total_rows = 0
    column_names = []
    null_counts = None
    first_chunk_for_stats = None

    try:
        with pd.read_csv(file_path, chunksize=chunk_size, low_memory=False, on_bad_lines='warn') as reader:
            for i, chunk in enumerate(reader):
                if i == 0:
                    column_names = chunk.columns.tolist()
                    null_counts = chunk.isnull().sum()
                    first_chunk_for_stats = chunk
                else:
                    null_counts += chunk.isnull().sum()
                
                total_rows += len(chunk)

        if total_rows == 0 or first_chunk_for_stats is None:
            logger.warning(f"File {file_path} appears to be empty or unreadable.")
            return None

        logger.info(f"Successfully processed {total_rows} total rows.")
        logger.info("Generating profiling statistics from a sample chunk...")
        
        logger.info(f"Sample rows from {os.path.basename(file_path)}:\n{first_chunk_for_stats.head().to_string()}")

        buf = StringIO()
        first_chunk_for_stats.info(buf=buf) 
        info_str = buf.getvalue()

        coverage = ((1 - (null_counts / total_rows)) * 100).round(2).to_dict()

        stats = {
            "file_name": os.path.basename(file_path),
            "total_rows": total_rows,
            "total_columns": len(column_names),
            "headers": column_names,
            "column_coverage_percent": coverage,
            "sample_info": info_str,
            "sample_descriptive_stats": first_chunk_for_stats.describe(include='all').to_string()
        }
        logger.info(f"Profiling complete for {os.path.basename(file_path)}.")
        return stats

    except Exception as e:
        logger.error(f"An error occurred while loading {file_path}: {e}", exc_info=True)
        return None

def main():
    """Main execution function for the EDA script."""
    logger.info("--- Starting Full Exploratory Data Analysis (EDA) on all CSV files ---")

    all_stats = {}
    data_dir = 'Data'
    logger.info(f"Scanning for CSV files in directory: {data_dir}")

    try:
        csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
        logger.info(f"Found {len(csv_files)} CSV files: {csv_files}")
    except FileNotFoundError:
        logger.error(f"Data directory '{data_dir}' not found. Halting analysis.")
        return

    for file_name in csv_files:
        file_path = os.path.join(data_dir, file_name)
        stats = load_and_profile_csv(file_path)
    
        if stats is not None:
            base_name = os.path.splitext(file_name)[0]
            all_stats[base_name] = stats
            
            logger.info(f"--- Profiling Results for {file_name} ---")
            logger.info(f"Shape: ({stats['total_rows']} rows, {stats['total_columns']} columns)")
            logger.info("Column Coverage:")
            for col, cov in stats['column_coverage_percent'].items():
                logger.info(f"  - {col}: {cov}%")
            logger.info("--- End of Profiling Results ---")
        else:
            logger.warning(f"Could not load or profile {file_name}. Skipping.")

    logger.info("--- EDA: Initial Loading and Profiling Complete ---")
    
if __name__ == "__main__":
    setup_logging()
    main()
