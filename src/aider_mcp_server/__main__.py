import argparse
import asyncio
from aider_mcp_server.server import serve
from aider_mcp_server.atoms.utils import DEFAULT_EDITOR_MODEL, DEFAULT_AIDER_TIMEOUT

def main():
    # Create the argument parser
    parser = argparse.ArgumentParser(description="Aider MCP Server - Offload AI coding tasks to Aider")
    
    # Add arguments
    parser.add_argument(
        "--editor-model", 
        type=str, 
        default=DEFAULT_EDITOR_MODEL,
        help=f"Editor model to use (default: {DEFAULT_EDITOR_MODEL})"
    )
    parser.add_argument(
        "--current-working-dir", 
        type=str, 
        required=True,
        help="Current working directory (must be a valid git repository)"
    )
    parser.add_argument(
        "--default-timeout",
        type=int,
        default=DEFAULT_AIDER_TIMEOUT,
        help=f"Default timeout for Aider operations in seconds (default: {DEFAULT_AIDER_TIMEOUT})"
    )
     
    args = parser.parse_args()
    
    # Run the server asynchronously
    asyncio.run(serve(
        editor_model=args.editor_model,
        current_working_dir=args.current_working_dir,
        default_timeout=args.default_timeout
    ))

if __name__ == "__main__":
    main()
