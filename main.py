#!/usr/bin/env python3
"""
IEMS 490 - LLM-Powered Coding Agent
Main entry point for the coding agent.

Usage:
    python main.py                          # Interactive mode
    python main.py "Your task here"         # Single task mode
    python main.py --task "Your task"       # Explicit task flag
    python main.py --auto-approve           # Skip permission prompts
    python main.py --model gemini-1.5-pro  # Use specific model
    python main.py --verbose                # Enable verbose logging
"""
import argparse
import os
import sys
from dotenv import load_dotenv

from agent.llm import LLMClient
from agent.permissions import PermissionManager
from agent.loop import CodingAgent


def main():
    # Load environment variables from .env file
    load_dotenv()
    
    parser = argparse.ArgumentParser(
        description="LLM-Powered Coding Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                              # Start interactive mode
  python main.py "Find all TODO comments"     # Run a single task
  python main.py --auto-approve               # Auto-approve dangerous actions
  python main.py --model gemini-1.5-pro              # Use Gemini 1.5 Pro instead of default
  python main.py --verbose "Read README.md"   # Verbose mode with task
        """
    )
    
    parser.add_argument(
        "task",
        nargs="?",
        help="Task to execute (if not provided, starts interactive mode)"
    )
    parser.add_argument(
        "--task-flag",
        dest="task_flag",
        help="Task to execute (alternative to positional argument)"
    )
    parser.add_argument(
        "--model",
        default="gemini-2.0-flash",
        help="LLM model to use (default: gemini-2.0-flash)"
    )
    parser.add_argument(
        "--provider",
        default="gemini",
        choices=["gemini", "openai"],
        help="LLM provider to use: 'gemini' or 'openai' (default: gemini)"
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key (falls back to GEMINI_API_KEY or OPENAI_API_KEY env var depending on provider)"
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Custom API base URL for OpenAI-compatible local models (e.g., http://localhost:11434/v1)"
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve all dangerous actions (use with caution!)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=30,
        help="Maximum agent loop iterations (default: 30)"
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace root directory. File operations are sandboxed to this path (default: current directory)"
    )
    
    args = parser.parse_args()
    
    # Determine the task
    task = args.task_flag or args.task
    
    # Check for API key
    if args.provider == "openai":
        api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("Error: No OpenAI API key provided.")
            print("Set OPENAI_API_KEY environment variable or use --api-key")
            sys.exit(1)
    else:
        api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("Error: No Gemini API key provided.")
            print("Set GEMINI_API_KEY environment variable or use --api-key")
            sys.exit(1)
    
    # Initialize components
    try:
        llm_client = LLMClient(
            provider=args.provider,
            api_key=api_key,
            model=args.model,
            base_url=args.base_url
        )
    except Exception as e:
        print(f"Error initializing LLM client: {e}")
        sys.exit(1)
    
    workspace = os.path.abspath(args.workspace)
    # Change current working directory to the workspace so all tools and subprocesses
    # automatically operate relative to the sandboxed workspace.
    os.chdir(workspace)
    
    permissions = PermissionManager(workspace=workspace, auto_approve=args.auto_approve)
    print(f"🔒 Workspace sandbox: {workspace}")
    
    agent = CodingAgent(
        llm_client=llm_client,
        permissions=permissions,
        max_iterations=args.max_iterations,
        verbose=args.verbose
    )
    
    # Run in appropriate mode
    if task:
        result = agent.run(task)
        print(f"\n{'='*70}")
        print("FINAL RESULT:")
        print(result)
    else:
        agent.run_interactive()


if __name__ == "__main__":
    main()
