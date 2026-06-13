"""Tool for reading file contents."""
import os
from .base import Tool


class FileReadTool(Tool):
    """Read the contents of a file given its path.

    Paths are resolved against the workspace by the permission manager
    before any I/O occurs, preventing reads outside the sandbox.
    """

    name = "file_read"
    description = "Read the contents of a file at the given path. Returns the file content as a string. Use this to examine source code, configs, logs, or any text file."
    danger_level = "safe"
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative path to the file to read."
            },
            "offset": {
                "type": "integer",
                "description": "Line number to start reading from (1-based). Default: 1.",
                "default": 1
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to read. Default: 500.",
                "default": 500
            }
        },
        "required": ["path"]
    }

    # Reference to the permission manager, injected at registration time
    _permissions = None

    def execute(self, path: str, offset: int = 1, limit: int = 500, **kwargs):
        """Read a file and return its contents.

        The path is resolved against the workspace first. If it escapes
        the sandbox a PermissionError is caught and returned as an error
        result instead of crashing the agent.
        """
        # ── Workspace sandboxing ──────────────────────────────────────
        if self._permissions:
            try:
                path = self._permissions.resolve_path(path)
            except PermissionError as e:
                return {
                    "success": False,
                    "error": str(e)
                }

        if not os.path.exists(path):
            return {
                "success": False,
                "error": f"File not found: {path}"
            }

        if not os.path.isfile(path):
            return {
                "success": False,
                "error": f"Path is not a file: {path}"
            }

        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()

            total_lines = len(lines)
            start = max(0, offset - 1)
            end = min(total_lines, start + limit)

            selected_lines = lines[start:end]
            content = ''.join(selected_lines)

            return {
                "success": True,
                "result": content,
                "metadata": {
                    "path": os.path.abspath(path),
                    "total_lines": total_lines,
                    "shown_lines": f"{start + 1}-{end}",
                    "file_size": os.path.getsize(path)
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to read file: {str(e)}"
            }
