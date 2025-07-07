import json
import logging
import os
import shutil
from contextlib import contextmanager
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class TestDataManager:
    """
    Manages the lifecycle of test data, including generation, loading, and cleanup.
    """

    def __init__(self, base_dir: str = "test_data"):
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)
        logger.info(f"Test data manager initialized with base directory: {self.base_dir}")

    def generate_data(self, data_type: str, count: int = 1, **kwargs) -> List[str]:
        """
        Generates synthetic test data based on type and count.
        For demonstration, this will create simple JSON files.
        """
        generated_files = []
        data_dir = os.path.join(self.base_dir, data_type)
        os.makedirs(data_dir, exist_ok=True)

        logger.info(f"Generating {count} items of '{data_type}' data...")
        for i in range(count):
            data = {"id": f"{data_type}_{i + 1}", "value": f"sample_value_{i + 1}", **kwargs}
            file_path = os.path.join(data_dir, f"{data_type}_{i + 1}.json")
            try:
                with open(file_path, "w") as f:
                    json.dump(data, f, indent=2)
                generated_files.append(file_path)
                logger.debug(f"Generated data file: {file_path}")
            except IOError as e:
                logger.error(f"Error writing data to {file_path}: {e}")
        logger.info(f"Finished generating {len(generated_files)} items of '{data_type}' data.")
        return generated_files

    def load_data(self, data_type: str, file_name: str = None) -> Dict[str, Any] | List[Dict[str, Any]]:
        """
        Loads test data from a specific file or all files of a given type.
        """
        data_dir = os.path.join(self.base_dir, data_type)
        if not os.path.exists(data_dir):
            logger.warning(f"Data directory for '{data_type}' not found: {data_dir}")
            return []

        if file_name:
            file_path = os.path.join(data_dir, file_name)
            if not os.path.exists(file_path):
                logger.error(f"Data file not found: {file_path}")
                return {}
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                logger.info(f"Loaded data from {file_path}")
                return data
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON from {file_path}: {e}")
                return {}
            except IOError as e:
                logger.error(f"Error reading data from {file_path}: {e}")
                return {}
        else:
            all_data = []
            for f_name in os.listdir(data_dir):
                if f_name.endswith(".json"):
                    file_path = os.path.join(data_dir, f_name)
                    try:
                        with open(file_path, "r") as f:
                            all_data.append(json.load(f))
                    except (json.JSONDecodeError, IOError) as e:
                        logger.error(f"Error processing {file_path}: {e}")
            logger.info(f"Loaded {len(all_data)} items of '{data_type}' data.")
            return all_data

    def cleanup_data(self, data_type: str = None):
        """
        Cleans up generated test data. If data_type is None, cleans up all data.
        """
        if data_type:
            path_to_clean = os.path.join(self.base_dir, data_type)
            if os.path.exists(path_to_clean):
                try:
                    shutil.rmtree(path_to_clean)
                    logger.info(f"Cleaned up data directory: {path_to_clean}")
                except OSError as e:
                    logger.error(f"Error cleaning up {path_to_clean}: {e}")
            else:
                logger.warning(f"No data directory found to clean up for '{data_type}': {path_to_clean}")
        else:
            if os.path.exists(self.base_dir):
                try:
                    shutil.rmtree(self.base_dir)
                    logger.info(f"Cleaned up all test data in base directory: {self.base_dir}")
                except OSError as e:
                    logger.error(f"Error cleaning up base directory {self.base_dir}: {e}")
            else:
                logger.warning(f"No base data directory found to clean up: {self.base_dir}")

    @contextmanager
    def data_context(self, data_type: str, count: int = 1, **kwargs):
        """
        A context manager to generate data before a test and clean it up afterwards.
        Yields the paths to the generated files.
        """
        generated_files = []
        try:
            logger.info(f"Entering data context for '{data_type}'...")
            generated_files = self.generate_data(data_type, count, **kwargs)
            yield generated_files
        finally:
            logger.info(f"Exiting data context for '{data_type}', cleaning up...")
            self.cleanup_data(data_type)
