"""Tool for executing shell commands."""
import subprocess
import shlex
import os
from .base import Tool


class ShellExecuteTool(Tool):
    """Execute a shell command and capture stdout/stderr."""
    
    name = "shell_execute"
    description = "Execute a shell command and return stdout, stderr, and exit code. Use for running tests, checking git status, listing directories, installing packages, etc. WARNING: Can be dangerous - be careful with destructive commands like rm, dd, etc."
    danger_level = "dangerous"
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute."
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for the command. Defaults to current directory.",
                "default": "."
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds. Default: 60.",
                "default": 60
            }
        },
        "required": ["command"]
    }
    
    # Commands that require extra confirmation
    DANGEROUS_PATTERNS = [
        'rm -rf', 'rm -r /', 'dd if=', '> /dev/sd', ':(){:|:&};:',
        'mkfs.', 'curl.*|.*sh', 'wget.*|.*sh',
        'chmod -R 777 /', 'chown -R',
    ]
    
    # Reference to the permission manager, injected at registration time
    _permissions = None

    def execute(self, command: str, cwd: str = ".", timeout: int = 60, **kwargs):
        """Execute a shell command safely."""
        # ── Workspace sandboxing ──────────────────────────────────────
        if self._permissions:
            try:
                cwd = self._permissions.resolve_path(cwd)
            except PermissionError as e:
                return {
                    "success": False,
                    "error": str(e)
                }

        # Check for obviously dangerous patterns
        cmd_lower = command.lower()
        for pattern in self.DANGEROUS_PATTERNS:
            import re
            if re.search(pattern, cmd_lower):
                return {
                    "success": False,
                    "error": f"Command matches dangerous pattern and is blocked: {pattern}",
                    "result": "BLOCKED_FOR_SAFETY"
                }
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR]:\n{result.stderr}"
            
            return {
                "success": result.returncode == 0,
                "result": output if output else "(no output)",
                "metadata": {
                    "command": command,
                    "cwd": os.path.abspath(cwd),
                    "exit_code": result.returncode,
                    "stdout_length": len(result.stdout),
                    "stderr_length": len(result.stderr)
                }
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Command timed out after {timeout} seconds",
                "result": "TIMEOUT"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to execute command: {str(e)}"
            }
