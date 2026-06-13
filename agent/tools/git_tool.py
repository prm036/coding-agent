"""Tool for git operations."""
import subprocess
import os
from .base import Tool


def _run_git(command, cwd=".", timeout=30):
    """Helper to run git commands."""
    result = subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout
    )
    return result


class GitTool(Tool):
    """Execute git commands like status, diff, add, commit, etc."""
    
    name = "git"
    description = "Execute git commands to check repository status, view diffs, or perform git operations. Common commands: 'status', 'diff', 'log --oneline -5', 'branch'. Use for inspecting code changes."
    danger_level = "dangerous"
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The git subcommand to run (e.g., 'status', 'diff', 'log --oneline -5'). Do NOT include 'git' prefix."
            },
            "cwd": {
                "type": "string",
                "description": "Working directory containing the git repo. Default: current directory.",
                "default": "."
            }
        },
        "required": ["command"]
    }
    
    # Reference to the permission manager, injected at registration time
    _permissions = None

    def execute(self, command: str, cwd: str = ".", **kwargs):
        """Execute a git command."""
        # ── Workspace sandboxing ──────────────────────────────────────
        if self._permissions:
            try:
                cwd = self._permissions.resolve_path(cwd)
            except PermissionError as e:
                return {
                    "success": False,
                    "error": str(e)
                }

        if any(op in command for op in ["&&", "||", ";"]):
            return {
                "success": False,
                "error": "Do not chain commands using &&, ||, or ;. Run one git command per tool call."
            }
            
        try:
            # Check if we're in a git repo
            check = _run_git("git rev-parse --git-dir", cwd=cwd)
            if check.returncode != 0:
                return {
                    "success": False,
                    "error": f"Not a git repository: {os.path.abspath(cwd)}"
                }
            
            result = _run_git(f"git {command}", cwd=cwd)
            
            output = result.stdout
            if result.stderr and "warning" not in result.stderr.lower():
                output += f"\n[STDERR]:\n{result.stderr}"
            
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": output if output.strip() else f"Command failed with exit code {result.returncode}",
                    "metadata": {
                        "command": f"git {command}",
                        "cwd": os.path.abspath(cwd),
                        "exit_code": result.returncode
                    }
                }
            
            return {
                "success": True,
                "result": output if output else "(no output)",
                "metadata": {
                    "command": f"git {command}",
                    "cwd": os.path.abspath(cwd),
                    "exit_code": result.returncode
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Git command failed: {str(e)}"
            }
