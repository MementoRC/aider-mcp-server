import json
import sys
import os
import asyncio
import subprocess
import logging
from typing import Dict, Any, Optional, List, Tuple, Union

import mcp
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

import time
from aider_mcp_server.atoms.logging import get_logger
from aider_mcp_server.atoms.utils import DEFAULT_EDITOR_MODEL, DEFAULT_AIDER_TIMEOUT
from aider_mcp_server.atoms.tools.aider_ai_code import code_with_aider
from aider_mcp_server.atoms.tools.aider_list_models import list_models

# Configure logging
logger = get_logger(__name__)

# Define MCP tools
AIDER_AI_CODE_TOOL = Tool(
    name="aider_ai_code",
    description="Run Aider to perform AI coding tasks based on the provided prompt and files",
    inputSchema={
        "type": "object",
        "properties": {
            "ai_coding_prompt": {
                "type": "string",
                "description": "The prompt for the AI to execute",
            },
            "relative_editable_files": {
                "type": "array",
                "description": "LIST of relative paths to files that can be edited",
                "items": {"type": "string"},
            },
            "relative_readonly_files": {
                "type": "array",
                "description": "LIST of relative paths to files that can be read but not edited, add files that are not editable but useful for context",
                "items": {"type": "string"},
            },
            "model": {
                "type": "string",
                "description": "The primary AI model Aider should use for generating code, leave blank unless model is specified in the request",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": f"Optional timeout in seconds for the Aider operation (default: {DEFAULT_AIDER_TIMEOUT})",
                "minimum": 1,
            },
        },
        "required": ["ai_coding_prompt", "relative_editable_files"],
    },
)

LIST_MODELS_TOOL = Tool(
    name="list_models",
    description="List available models that match the provided substring",
    inputSchema={
        "type": "object",
        "properties": {
            "substring": {
                "type": "string",
                "description": "Substring to match against available models",
            }
        },
    },
)


def is_git_repository(directory: str) -> Tuple[bool, Union[str, None]]:
    """
    Check if the specified directory is a git repository.

    Args:
        directory (str): The directory to check.

    Returns:
        Tuple[bool, Union[str, None]]: A tuple containing a boolean indicating if it's a git repo,
                                      and an error message if it's not.
    """
    try:
        # Make sure the directory exists
        if not os.path.isdir(directory):
            return False, f"Directory does not exist: {directory}"

        # Use the git command with -C option to specify the working directory
        # This way we don't need to change our current directory
        result = subprocess.run(
            ["git", "-C", directory, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0 and result.stdout.strip() == "true":
            return True, None
        else:
            return False, result.stderr.strip() or "Directory is not a git repository"

    except subprocess.SubprocessError as e:
        return False, f"Error checking git repository: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error checking git repository: {str(e)}"


def process_aider_ai_code_request( # noqa: E501
    params: Dict[str, Any],
    editor_model: str,
    current_working_dir: str,
    default_timeout: int,
) -> Dict[str, Any]:
    """
    Process an aider_ai_code request. # noqa: E501

    Args:
        params (Dict[str, Any]): The request parameters. # noqa: E501
        editor_model (str): The editor model to use. # noqa: E501
        current_working_dir (str): The current working directory where git repo is located. # noqa: E501
        default_timeout (int): The default timeout in seconds to use if not specified in params. # noqa: E501

    Returns:
        Dict[str, Any]: The response data. # noqa: E501
    """
    ai_coding_prompt = params.get("ai_coding_prompt", "")
    relative_editable_files = params.get("relative_editable_files", [])
    relative_readonly_files = params.get("relative_readonly_files", [])

    # Ensure relative_editable_files is a list
    if isinstance(relative_editable_files, str):
        logger.info(
            f"Converting single editable file string to list: {relative_editable_files}"
        )
        relative_editable_files = [relative_editable_files]

    # Ensure relative_readonly_files is a list
    if isinstance(relative_readonly_files, str):
        logger.info(
            f"Converting single readonly file string to list: {relative_readonly_files}"
        )
        relative_readonly_files = [relative_readonly_files]

    # Get the model from request parameters if provided
    request_model = params.get("model")
    # Get the timeout from request parameters
    timeout_seconds = params.get("timeout_seconds")

    # Validate timeout if provided, otherwise use the default
    if timeout_seconds is not None: # noqa: E501
        # Explicitly reject float values
        if isinstance(timeout_seconds, float): # noqa: E501
            logger.warning( # noqa: E501
                f"Invalid timeout value type: float ({timeout_seconds}). " # noqa: E501
                f"Timeout must be an integer. Using default ({default_timeout}s)." # noqa: E501
            ) # noqa: E501
            timeout_seconds = default_timeout # noqa: E501
        # Try to convert other types to int and validate
        else: # noqa: E501
            try: # noqa: E501
                timeout_seconds = int(timeout_seconds) # noqa: E501
                if timeout_seconds <= 0: # noqa: E501
                    logger.warning( # noqa: E501
                        f"Invalid timeout value: non-positive integer ({timeout_seconds}). " # noqa: E501
                        f"Timeout must be positive. Using default ({default_timeout}s)." # noqa: E501
                    ) # noqa: E501
                    timeout_seconds = default_timeout # noqa: E501
            except (ValueError, TypeError): # noqa: E501
                logger.warning( # noqa: E501
                    f"Invalid timeout value type ({timeout_seconds}). " # noqa: E501
                    f"Timeout must be an integer. Using default ({default_timeout}s)." # noqa: E501
                ) # noqa: E501
                timeout_seconds = default_timeout # noqa: E501
    else:
        # No timeout provided in request, use the default
        timeout_seconds = default_timeout
        logger.info(f"No timeout specified in request, using default: {timeout_seconds} seconds")


    # Log the request details
    logger.info(f"AI Coding Request: Prompt: '{ai_coding_prompt}'")
    logger.info(f"Editable files: {relative_editable_files}")
    logger.info(f"Readonly files: {relative_readonly_files}")
    logger.info(f"Editor model: {editor_model}")
    if request_model:
        logger.info(f"Request-specified model: {request_model}")
    if timeout_seconds is not None:
        logger.info(f"Request-specified timeout: {timeout_seconds} seconds")

    # Use the model specified in the request if provided, otherwise use the editor model
    model_to_use = request_model if request_model else editor_model

    # Use the passed-in current_working_dir parameter
    logger.info(f"Using working directory for code_with_aider: {current_working_dir}")

    result_json = code_with_aider(
        ai_coding_prompt=ai_coding_prompt,
        relative_editable_files=relative_editable_files,
        relative_readonly_files=relative_readonly_files,
        model=model_to_use,
        working_dir=current_working_dir,
        timeout_seconds=timeout_seconds, # Pass the validated timeout
    )

    # Parse the JSON string result
    try:
        result_dict = json.loads(result_json)
    except json.JSONDecodeError as e:
        logger.error(f"Error: Failed to parse JSON response from code_with_aider: {e}")
        logger.error(f"Received raw response: {result_json}")
        return {"error": "Failed to process AI coding result"}

    logger.info(
        f"AI Coding Request Completed. Success: {result_dict.get('success', False)}"
    )
    return {
        "success": result_dict.get("success", False),
        "diff": result_dict.get("diff", "Error retrieving diff"),
    }


def process_list_models_request(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a list_models request.

    Args:
        params (Dict[str, Any]): The request parameters.

    Returns:
        Dict[str, Any]: The response data.
    """
    substring = params.get("substring", "")

    # Log the request details
    logger.info(f"List Models Request: Substring: '{substring}'")

    models = list_models(substring)
    logger.info(f"Found {len(models)} models matching '{substring}'")

    return {"models": models}


def handle_request( # noqa: E501
    request: Dict[str, Any], # noqa: E501
    current_working_dir: str, # noqa: E501
    editor_model: str, # noqa: E501
    default_timeout: int, # noqa: E501
) -> Dict[str, Any]: # noqa: E501
    """
    Handle incoming MCP requests according to the MCP protocol. # noqa: E501

    Args:
        request (Dict[str, Any]): The request JSON.
        current_working_dir (str): The current working directory. Must be a valid git repository.
        editor_model (str): The editor model to use.

    Returns:
        Dict[str, Any]: The response JSON.
    """
    try:
        # Validate current_working_dir is provided and is a git repository
        if not current_working_dir:
            error_msg = "Error: current_working_dir is required. Please provide a valid git repository path."
            logger.error(error_msg)
            return {"error": error_msg}

        # MCP protocol requires 'name' and 'parameters' fields
        if "name" not in request:
            logger.error("Error: Received request missing 'name' field.")
            return {"error": "Missing 'name' field in request"}

        request_type = request.get("name")
        params = request.get("parameters", {})

        logger.info(
            f"Received request: Type='{request_type}', CWD='{current_working_dir}'"
        )

        # Validate that the current_working_dir is a git repository before changing to it
        is_git_repo, error_message = is_git_repository(current_working_dir)
        if not is_git_repo:
            error_msg = f"Error: The specified directory '{current_working_dir}' is not a valid git repository: {error_message}"
            logger.error(error_msg)
            return {"error": error_msg}

        # Set working directory
        logger.info(f"Changing working directory to: {current_working_dir}")
        os.chdir(current_working_dir)

        # Route to the appropriate handler based on request type
        if request_type == "aider_ai_code":
            return process_aider_ai_code_request( # noqa: E501
                params, editor_model, current_working_dir, default_timeout # Pass default_timeout # noqa: E501
            ) # noqa: E501

        elif request_type == "list_models":
            return process_list_models_request(params)

        else:
            # Unknown request type
            logger.warning(f"Warning: Unknown request type received: {request_type}")
            return {"error": f"Unknown request type: {request_type}"}

    except Exception as e:
        # Handle any errors
        logger.exception(
            f"Critical Error: Unhandled exception during request processing: {str(e)}"
        )
        return {"error": f"Internal server error: {str(e)}"}


async def serve( # noqa: E501
    editor_model: str = DEFAULT_EDITOR_MODEL, # noqa: E501
    current_working_dir: str = None, # noqa: E501
    default_timeout: int = DEFAULT_AIDER_TIMEOUT, # noqa: E501
) -> None:
    """
    Start the MCP server following the Model Context Protocol. # noqa: E501

    The server reads JSON requests from stdin and writes JSON responses to stdout.
    Each request should contain a 'name' field indicating the tool to invoke, and
    a 'parameters' field with the tool-specific parameters.

    Args: # noqa: E501
        editor_model (str, optional): The editor model to use. Defaults to DEFAULT_EDITOR_MODEL. # noqa: E501
        current_working_dir (str, required): The current working directory. Must be a valid git repository. # noqa: E501
        default_timeout (int, optional): Default timeout for Aider operations in seconds. Defaults to DEFAULT_AIDER_TIMEOUT. # noqa: E501

    Raises: # noqa: E501
        ValueError: If current_working_dir is not provided or is not a git repository. # noqa: E501
    """
    logger.info("Starting Aider MCP Server") # noqa: E501
    logger.info(f"Editor Model: {editor_model}") # noqa: E501
    logger.info(f"Default Timeout: {default_timeout} seconds") # noqa: E501

    # Validate current_working_dir is provided
    if not current_working_dir: # noqa: E501
        error_msg = "Error: current_working_dir is required. Please provide a valid git repository path."
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info(f"Initial Working Directory: {current_working_dir}")

    # Validate that the current_working_dir is a git repository
    is_git_repo, error_message = is_git_repository(current_working_dir)
    if not is_git_repo:
        error_msg = f"Error: The specified directory '{current_working_dir}' is not a valid git repository: {error_message}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info(f"Validated git repository at: {current_working_dir}")

    # Set working directory
    logger.info(f"Setting working directory to: {current_working_dir}")
    os.chdir(current_working_dir)

    # Create the MCP server
    server = Server("aider-mcp-server")

    @server.list_tools()
    async def list_tools() -> List[Tool]:
        """Register all available tools with the MCP server."""
        return [AIDER_AI_CODE_TOOL, LIST_MODELS_TOOL]

    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle tool calls from the MCP client."""
        logger.info(f"Received Tool Call: Name='{name}'")
        logger.info(f"Arguments: {arguments}")

        try:
            if name == "aider_ai_code": # noqa: E501
                logger.info("Processing 'aider_ai_code' tool call...") # noqa: E501
                result = process_aider_ai_code_request( # noqa: E501
                    arguments, editor_model, current_working_dir, default_timeout # Pass default_timeout # noqa: E501
                ) # noqa: E501
                return [TextContent(type="text", text=json.dumps(result))] # noqa: E501

            elif name == "list_models": # noqa: E501
                logger.info(f"Processing 'list_models' tool call...")
                result = process_list_models_request(arguments)
                return [TextContent(type="text", text=json.dumps(result))]

            else:
                logger.warning(f"Warning: Received call for unknown tool: {name}")
                return [
                    TextContent(
                        type="text", text=json.dumps({"error": f"Unknown tool: {name}"})
                    )
                ]

        except Exception as e:
            logger.exception(f"Error: Exception during tool call '{name}': {e}")
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {"error": f"Error processing tool {name}: {str(e)}"}
                    ),
                )
            ]

    # Initialize and run the server
    try:
        options = server.create_initialization_options()
        logger.info("Initializing stdio server connection...")
        async with stdio_server() as (read_stream, write_stream):
            logger.info("Server running. Waiting for requests...")
            await server.run(read_stream, write_stream, options, raise_exceptions=True)
    except Exception as e:
        logger.exception(
            f"Critical Error: Server stopped due to unhandled exception: {e}"
        )
        raise
    finally:
        logger.info("Aider MCP Server shutting down.")
