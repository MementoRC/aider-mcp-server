import logging
import os
import subprocess
import time
from typing import Any, Callable, Dict

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class E2ETestRunner:
    """
    Manages the execution of End-to-End tests, including environment setup and teardown.
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config if config is not None else {}
        self.processes: Dict[str, subprocess.Popen] = {}
        logger.info("E2E Test Runner initialized.")

    def _run_command(self, command: str, cwd: str = None, timeout: int = 60) -> bool:
        """Helper to run a shell command and check its success."""
        logger.info(f"Executing command: {command} in {cwd if cwd else os.getcwd()}")
        try:
            # Split command for security - avoid shell=True with user input
            # S602: subprocess call with shell=True is a security risk
            # Here we control the command, but split for better security
            cmd_parts = command.split()
            process = subprocess.run(  # noqa: S603
                cmd_parts, check=True, capture_output=True, text=True, cwd=cwd, timeout=timeout
            )
            logger.debug(f"Command stdout:\n{process.stdout}")
            if process.stderr:
                logger.warning(f"Command stderr:\n{process.stderr}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed with exit code {e.returncode}: {command}")
            logger.error(f"Stdout: {e.stdout}")
            logger.error(f"Stderr: {e.stderr}")
            return False
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out after {timeout} seconds: {command}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred while running command '{command}': {e}")
            return False

    def setup_environment(self) -> bool:
        """
        Sets up the environment for E2E tests. This might involve starting services,
        deploying applications, etc.
        """
        logger.info("Setting up E2E test environment...")
        # Example: Start a dummy web server or a mock service
        # In a real scenario, this would start your actual application components.
        try:
            # Simulate starting a server process
            # For a real app, replace with actual startup command, e.g., "uvicorn app:app --port 8000"
            # This example uses a simple Python HTTP server for demonstration
            server_command = ["python", "-m", "http.server", "8000"]
            logger.info(f"Starting mock server: {' '.join(server_command)}")
            # S603: subprocess call with shell=False is safer than shell=True
            self.processes["mock_server"] = subprocess.Popen(  # noqa: S603
                server_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            time.sleep(2)  # Give server time to start
            logger.info("E2E test environment setup complete.")
            return True
        except Exception as e:
            logger.error(f"Failed to set up E2E environment: {e}")
            self.teardown_environment()  # Attempt cleanup
            return False

    def run_e2e_test(self, test_function: Callable, *args, **kwargs) -> Dict[str, Any]:
        """
        Executes a single E2E test function.
        """
        test_name = test_function.__name__
        logger.info(f"Running E2E test: {test_name}")
        start_time = time.time()
        success = False
        error_message = None
        try:
            test_function(*args, **kwargs)
            success = True
            logger.info(f"E2E test '{test_name}' completed successfully.")
        except Exception as e:
            success = False
            error_message = str(e)
            logger.error(f"E2E test '{test_name}' failed: {e}", exc_info=True)

        end_time = time.time()
        duration = end_time - start_time
        return {"test_name": test_name, "success": success, "duration": duration, "error": error_message}

    def teardown_environment(self) -> bool:
        """
        Tears down the E2E test environment, stopping services and cleaning up.
        """
        logger.info("Tearing down E2E test environment...")
        all_stopped = True
        for name, process in self.processes.items():
            if process.poll() is None:  # Process is still running
                logger.info(f"Terminating process: {name} (PID: {process.pid})")
                try:
                    process.terminate()
                    process.wait(timeout=5)  # Give it some time to terminate
                    if process.poll() is None:  # Still running, try kill
                        logger.warning(f"Process {name} did not terminate, killing it.")
                        process.kill()
                        process.wait(timeout=5)
                except Exception as e:
                    logger.error(f"Error terminating process {name}: {e}")
                    all_stopped = False
            else:
                logger.info(f"Process {name} (PID: {process.pid}) already stopped.")
        self.processes.clear()
        logger.info("E2E test environment teardown complete.")
        return all_stopped
