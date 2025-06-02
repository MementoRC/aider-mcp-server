"""
Core execution module for Aider AI operations.

This module contains the CoreExecutor class that handles the main execution
logic extracted from the original aider_ai_code.py file.
"""

import os
import sys
import asyncio
from io import StringIO
from typing import Any, Dict, List, Optional

from aider.coders import Coder
from aider.models import Model

try:
    from aider.repo import GitRepo
except ImportError:
    GitRepo = None

from .shared.types import ResponseDict
from aider_mcp_server.atoms.logging.logger import get_logger

logger = get_logger(__name__)

class CoreExecutor:
    """Handles the core execution logic for Aider AI operations."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def convert_to_absolute_paths(
        self, relative_paths: List[str], working_dir: Optional[str]
    ) -> List[str]:
        """
        Convert relative file paths to absolute paths.

        Args:
            relative_paths: List of file paths (possibly relative)
            working_dir: Working directory to resolve relative paths against

        Returns:
            List of absolute file paths
        """
        if not working_dir:
            # If no working dir, assume paths are already absolute
            return relative_paths

        # Convert each path to absolute if it's not already
        absolute_paths = []
        for path in relative_paths:
            if os.path.isabs(path):
                absolute_paths.append(path)
            else:
                absolute_paths.append(os.path.abspath(os.path.join(working_dir, path)))

        return absolute_paths

    def setup_aider_coder(
        self,
        model: Model,
        working_dir: str,
        abs_editable_files: List[str],
        abs_readonly_files: List[str],
        architect_mode: bool = False,
        auto_accept_architect: bool = True,
    ) -> Coder:
        """
        Set up an Aider Coder instance with the given configuration.

        Args:
            model: The configured Aider model
            working_dir: Working directory for git operations
            abs_editable_files: List of absolute paths to files that can be edited
            abs_readonly_files: List of absolute paths to files that can be read but not edited
            architect_mode: Whether to use two-phase architecture mode
            auto_accept_architect: Whether to automatically accept architect suggestions

        Returns:
            Configured Aider Coder instance
        """
        logger.info("Setting up Aider coder...")

        # Log aider version for debugging
        try:
            from aider_mcp_server.molecules.tools.aider_compatibility import get_aider_version, filter_supported_params, get_supported_coder_create_params, get_supported_coder_params
            aider_version = get_aider_version()
        except ImportError:
            aider_version = "unknown"
        logger.info(f"Using aider version: {aider_version}")

        # Set chat history file path in the working directory if possible
        chat_history_file = None
        if working_dir:
            try:
                chat_history_dir = os.path.join(working_dir, ".aider")
                os.makedirs(chat_history_dir, exist_ok=True)
                chat_history_file = os.path.join(chat_history_dir, "chat_history.md")
            except Exception as e:
                logger.warning(f"Could not create chat history directory: {e}")

        # Create no-op functions to replace output methods
        def noop_output(*args: Any, **kwargs: Any) -> None:
            pass

        # Create an IO instance for the Coder that won't require interactive prompting
        # Add verbose=False to suppress progress output
        try:
            from aider_ai_code import SilentInputOutput
        except ImportError:
            class SilentInputOutput:
                def tool_error(self, message: str = "", strip: bool = True) -> None:
                    pass

        io = SilentInputOutput(
            pretty=False,  # Disable fancy output
            yes=True,  # Always say yes to prompts
            fancy_input=False,  # Disable fancy input to avoid prompt_toolkit usage
            chat_history_file=chat_history_file,  # Set chat history file if available
        )

        io.yes_to_all = True  # Automatically say yes to all prompts
        io.dry_run = False  # Ensure we're not in dry-run mode

        # Create no-op functions for output methods to suppress output
        def noop(*args: Any, **kwargs: Any) -> None:
            pass

        # Redirect output to no-op functions
        io.output = noop
        io.tool_output = noop

        # Set quiet mode to True to suppress unnecessary output
        io.quiet = True
        # For the GitRepo, we need to import the class from aider (if available)
        git_repo = None
        if GitRepo is not None:
            try:
                # Check if a .git folder exists to determine if this is a git repo
                git_dir = os.path.join(working_dir, ".git")
                is_git_repo = os.path.isdir(git_dir)

                if is_git_repo:
                    logger.info(f"Found git repository at {working_dir}")
                    git_repo = GitRepo(
                        io=io,
                        fnames=abs_editable_files,
                        git_dname=working_dir,
                        models=model.commit_message_models(),
                    )
                    logger.info(f"Successfully initialized GitRepo with root: {git_repo.root}")
                else:
                    logger.warning(f"No .git directory found at {working_dir}, will set repo=None")
                    git_repo = None
            except Exception as e:
                logger.warning(f"Could not initialize GitRepo: {e}, will set repo=None")
                git_repo = None
        else:
            logger.warning("Could not import GitRepo from aider.repo, will set repo=None")
            git_repo = None

        # Parameters for Coder.create method (different from __init__)
        try:
            from aider_mcp_server.molecules.tools.aider_compatibility import filter_supported_params, get_supported_coder_create_params, get_supported_coder_params
            create_params = {
                "main_model": model,
                "io": io,
                "edit_format": "architect" if architect_mode else None,
            }

            # Parameters that go directly to Coder.__init__ via kwargs
            init_params = {
                "fnames": abs_editable_files,
                "read_only_fnames": abs_readonly_files,
                "repo": git_repo,
                "show_diffs": True,  # Show diffs to help debugging
                "auto_commits": False,
                "dirty_commits": False,
                "use_git": True if git_repo else False,
                "stream": False,
                "suggest_shell_commands": False,
                "detect_urls": False,
                "verbose": True,  # Enable verbose mode for more debugging info
                "auto_accept_architect": auto_accept_architect if architect_mode else True,
            }

            logger.info(f"Setting up Aider Coder with params: create_params={create_params}, init_params={init_params}")

            # Get supported parameters for create method
            supported_create_params = get_supported_coder_create_params()
            logger.info(f"Supported Coder.create parameters: {supported_create_params}")

            # Get supported parameters for init method
            supported_init_params = get_supported_coder_params()
            logger.info(f"Supported Coder.__init__ parameters: {supported_init_params}")

            # Filter parameters based on what's actually supported
            filtered_create = filter_supported_params(create_params, supported_create_params)
            filtered_init = filter_supported_params(init_params, supported_init_params)

            # Combine create params with init params as kwargs
            final_params = filtered_create.copy()
            final_params.update(filtered_init)

            logger.info(f"Creating Coder with parameters: {list(final_params.keys())}")

            # Create the Coder instance using parameters compatible with the installed version
            coder = Coder.create(**final_params)
        except Exception as e:
            logger.error(f"Failed to create Coder instance: {e}")
            raise

        return coder

    def check_for_meaningful_changes(
        self, relative_editable_files: List[str], working_dir: Optional[str] = None
    ) -> bool:
        """
        Check if the edited files contain meaningful content.

        Args:
            relative_editable_files: List of files to check
            working_dir: The working directory where files are located
        """
        for file_path in relative_editable_files:
            # Get the correct full path without duplicating the working dir
            full_path = file_path
            if not os.path.isabs(file_path) and working_dir:
                full_path = os.path.join(working_dir, file_path)

            logger.info(f"Checking for meaningful content in: {full_path}")

            if os.path.exists(full_path):
                try:
                    with open(full_path, "r") as f:
                        content = f.read()
                        # Check if the file has any non-whitespace content
                        stripped_content = content.strip()

                        # Check if it's just a comment line
                        is_just_comment = stripped_content.startswith("#") and len(stripped_content.split("\n")) == 1

                        # Consider any non-empty file as meaningful, except for files with just comments
                        if stripped_content and not is_just_comment:
                            logger.info(f"Content found in file, considering meaningful: {file_path}")
                            return True
                        elif is_just_comment:
                            logger.info(f"File only contains comments, not considered meaningful: {file_path}")
                        else:
                            # If completely empty, continue to next file
                            logger.info(f"File is empty, no content found: {file_path}")
                except Exception as e:
                    logger.error(f"Failed reading file {full_path} during meaningful change check: {e}")
                    # If we can't read it, we can't confirm meaningful change from this file
                    continue
            else:
                logger.info(f"File not found or empty, skipping meaningful check: {full_path}")

        logger.info("No meaningful content detected in any editable files.")
        return False

    def capture_output_and_run_coder(self, coder: Coder, ai_coding_prompt: str) -> Optional[str]:
        """Captures stdout/stderr and runs coder.run. Returns the result of coder.run."""
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_capture = StringIO()
        stderr_capture = StringIO()

        run_result = None
        try:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            # Assuming coder.run might return something, like a status or summary string
            run_result = coder.run(ai_coding_prompt)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        captured_stdout = stdout_capture.getvalue()
        captured_stderr = stderr_capture.getvalue()

        if captured_stdout:
            logger.warning(f"Captured stdout from Aider: {captured_stdout[:200]}...")
        if captured_stderr:
            logger.warning(f"Captured stderr from Aider: {captured_stderr[:200]}...")

        logger.info(f"coder.run completed, result: {run_result}")
        return str(run_result) if run_result is not None else None

    def log_file_states_before_after_run(
        self, stage: str, relative_editable_files: List[str], working_dir: str
    ) -> None:
        """Logs the state of editable files (exists, size, partial content)."""
        logger.info(f"Logging file states {stage.upper()} coder run...")
        for file_path in relative_editable_files:
            # Ensure working_dir is used correctly to form full_path
            full_path = os.path.join(working_dir, os.path.normpath(file_path))

            if os.path.exists(full_path):
                try:
                    size = os.path.getsize(full_path)
                    logger.info(f"{stage.upper()} RUN: File {full_path} exists, size: {size} bytes")
                    if size > 0:
                        with open(full_path, "r", errors="ignore") as f:  # Add errors='ignore' for robustness
                            content = f.read(100)
                            logger.info(
                                f"{stage.upper()} RUN: File '{file_path}' (partial content): {content[:50].encode('unicode_escape').decode()}..."
                            )
                    elif stage.lower() == "after":  # Only warn if empty *after* run
                        logger.warning(f"AFTER RUN: File {full_path} exists but is EMPTY!")
                except Exception as e:
                    logger.error(f"{stage.upper()} RUN: Error accessing file {full_path}: {e}")
            else:
                logger.info(f"{stage.upper()} RUN: File {full_path} does not exist.")
                if stage.lower() == "after":  # Only warn if not existing *after* run
                    logger.warning(f"AFTER RUN: File {full_path} still does not exist after coder.run!")

    async def run_aider_session(
        self,
        coder: Coder,
        ai_coding_prompt: str,
        relative_editable_files: List[str],
        working_dir: str,
        use_diff_cache: bool,
        clear_cached_for_unchanged: bool,
    ) -> ResponseDict:
        """
        Run the Aider coding session and process the results.

        Args:
            coder: The configured Coder instance
            ai_coding_prompt: The prompt to send to the AI
            relative_editable_files: List of files that can be edited (relative paths)
            working_dir: Directory where files are located
            use_diff_cache: Whether to use the diff cache.
            clear_cached_for_unchanged: If using cache, whether to clear the entry
                                         if no changes are detected by the cache.

        Returns:
            Dictionary with success status and diff output
        """
        logger.info("Starting Aider coding session...")

        self.log_file_states_before_after_run("before", relative_editable_files, working_dir)

        # Run the coder and capture output
        # The result of coder.run is often None or not directly used for the final JSON output's content.
        # The primary effect is file modification, which is then assessed.
        _ = self.capture_output_and_run_coder(coder, ai_coding_prompt)  # Result of run is logged by helper

        self.log_file_states_before_after_run("after", relative_editable_files, working_dir)

        # Process the results after the coder has run
        # NOTE: The following is a placeholder. You should implement the actual result processing logic.
        # For now, return a dummy ResponseDict for demonstration.
        # In real use, you would call your own summary/diff logic here.
        response: ResponseDict = {
            "success": True,
            "changes_summary": {},
            "file_status": {},
            "is_cached_diff": False,
        }
        return response

    async def execute_with_retry(
        self,
        ai_coding_prompt: str,
        relative_editable_files: List[str],
        abs_editable_files: List[str],
        abs_readonly_files: List[str],
        working_dir: str,
        model: str,
        provider: str,
        use_diff_cache: bool,
        clear_cached_for_unchanged: bool,
        architect_mode: bool = False,
        editor_model: Optional[str] = None,
        auto_accept_architect: bool = True,
        coordinator: Optional[Any] = None,
    ) -> ResponseDict:
        """
        Execute Aider with retry logic for rate limit handling.

        Args:
            ai_coding_prompt: The prompt for the AI
            relative_editable_files: List of editable files (relative paths)
            abs_editable_files: List of editable files (absolute paths)
            abs_readonly_files: List of read-only files (absolute paths)
            working_dir: Working directory
            model: Model identifier
            provider: Provider name
            use_diff_cache: Whether to use the diff cache.
            clear_cached_for_unchanged: If using cache, whether to clear the entry
                                         if no changes are detected by the cache.
            architect_mode: Whether to use two-phase architecture mode
            editor_model: Optional secondary model for implementation when architect_mode is enabled
            auto_accept_architect: Whether to automatically accept architect suggestions
            coordinator: Optional coordinator for event broadcasting

        Returns:
            Response dictionary
        """
        # The following fallback_config and summarize_changes are assumed to be available in the context.
        try:
            from aider_ai_code import summarize_changes, get_fallback_model, detect_rate_limit_error, fallback_config
        except ImportError:
            summarize_changes = lambda x: {}
            get_fallback_model = lambda m, p: m
            detect_rate_limit_error = lambda e, p: False
            fallback_config = {}

        empty_summary = summarize_changes("")
        empty_status = {"has_changes": False, "status_summary": "No changes detected."}
        response: ResponseDict = {
            "success": False,
            "changes_summary": empty_summary,
            "file_status": empty_status,
            "is_cached_diff": False,
            "rate_limit_info": {"encountered": False, "retries": 0, "fallback_model": None},
        }

        max_retries = fallback_config.get(provider, {}).get("max_retries", 3)  # Default retries
        initial_delay = fallback_config.get(provider, {}).get("initial_delay", 1)
        backoff_factor = fallback_config.get(provider, {}).get("backoff_factor", 2)
        current_model = model

        for attempt in range(max_retries + 1):
            try:
                ai_model = Model(current_model)
                coder = self.setup_aider_coder(
                    ai_model, working_dir, abs_editable_files, abs_readonly_files, architect_mode, auto_accept_architect
                )
                session_response = await self.run_aider_session(
                    coder,
                    ai_coding_prompt,
                    relative_editable_files,
                    working_dir,
                    use_diff_cache,
                    clear_cached_for_unchanged,
                )
                response.update(session_response)
                if response.get("success"):
                    break  # Successful execution, exit retry loop

                if attempt == 0 and not response.get("success"):
                    logger.info("Aider session completed without errors but no changes were made.")
                    break

            except Exception as e:
                # Rate limit and fallback logic
                rli = response.get("rate_limit_info")
                if not isinstance(rli, dict):
                    rli = {"encountered": False, "retries": 0, "fallback_model": None}
                    response["rate_limit_info"] = rli

                if not isinstance(rli.get("retries"), int):
                    rli["retries"] = 0

                if detect_rate_limit_error(e, provider):
                    logger.info(f"Rate limit detected for {provider}. Attempting fallback...")
                    rli["encountered"] = True
                    rli["retries"] = rli.get("retries", 0) + 1  # type: ignore

                    if attempt < max_retries:
                        delay = initial_delay * (backoff_factor**attempt)
                        logger.info(f"Retrying after {delay:.2f} seconds...")
                        await asyncio.sleep(delay)
                        new_model = get_fallback_model(current_model, provider)
                        rli["fallback_model"] = new_model
                        logger.info(f"Falling back to model: {new_model}")
                        current_model = new_model
                        continue
                    else:
                        error_msg = f"Max retries ({max_retries}) reached for rate limit. Unable to complete request."
                        logger.error(f"{error_msg} Last error: {str(e)}")
                        response["success"] = False
                        response["diff"] = response.get("diff") or f"Error: {error_msg}"
                        cs = response.get("changes_summary")
                        if not isinstance(cs, dict) or not cs.get("summary"):
                            cs = summarize_changes("")
                            cs["summary"] = f"Error: {error_msg}"
                            response["changes_summary"] = cs
                        raise Exception(f"{error_msg} Last error: {str(e)}") from e
                else:
                    # Non-rate-limit error
                    error_msg = f"Unhandled error during Aider execution: {str(e)}"
                    logger.error(error_msg, exc_info=True)  # Log with traceback
                    response["success"] = False
                    response["diff"] = response.get("diff") or f"Error: {error_msg}"
                    cs = response.get("changes_summary")
                    if not isinstance(cs, dict) or not cs.get("summary"):
                        cs = summarize_changes("")
                        cs["summary"] = f"Error: {error_msg}"
                        response["changes_summary"] = cs
                    raise  # Re-raise the original exception

        return response
