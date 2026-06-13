"""Tool for writing and editing files."""
import os
import shutil
from .base import Tool


class FileWriteTool(Tool):
    """Create a new file or overwrite an existing file with the given content.

    Paths are resolved against the workspace by the permission manager
    before any I/O occurs, preventing writes outside the sandbox.
    """

    name = "file_write"
    description = "Create a new file or overwrite an existing file with the given content. Use for creating new source files, configs, or writing generated code. BE CAREFUL: this will overwrite existing files!"
    danger_level = "dangerous"
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path where the file should be written."
            },
            "content": {
                "type": "string",
                "description": "Full content to write to the file."
            }
        },
        "required": ["path", "content"]
    }

    # Reference to the permission manager, injected at registration time
    _permissions = None

    def execute(self, path: str, content: str, **kwargs):
        """Write content to a file.

        The path is resolved against the workspace first. If it escapes
        the sandbox a PermissionError is caught and returned as an error.
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

        try:
            # Ensure directory exists
            dir_name = os.path.dirname(path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)

            # Backup existing file if it exists
            backup_path = None
            if os.path.exists(path) and os.path.isfile(path):
                backup_path = path + ".backup"
                shutil.copy2(path, backup_path)

            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)

            result = {
                "success": True,
                "result": f"File written successfully: {os.path.abspath(path)}",
                "metadata": {
                    "path": os.path.abspath(path),
                    "bytes_written": len(content.encode('utf-8')),
                    "action": "overwritten" if backup_path else "created"
                }
            }
            if backup_path:
                result["metadata"]["backup"] = backup_path

            return result
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to write file: {str(e)}"
            }


class FileEditTool(Tool):
    """Edit a specific part of a file by replacing old text with new text.

    Paths are resolved against the workspace by the permission manager
    before any I/O occurs, preventing edits outside the sandbox.
    """

    name = "file_edit"
    description = "Edit a file by replacing a specific string with another string. Use for targeted changes like fixing a bug in one function without rewriting the entire file."
    danger_level = "dangerous"
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to edit."
            },
            "old_string": {
                "type": "string",
                "description": "The exact text to find and replace. Must match uniquely in the file. If replacing a common word like 'pass', include surrounding lines (like the function definition) so it is unique."
            },
            "new_string": {
                "type": "string",
                "description": "The text to replace old_string with."
            }
        },
        "required": ["path", "old_string", "new_string"]
    }

    # Reference to the permission manager, injected at registration time
    _permissions = None

    def execute(self, path: str, old_string: str, new_string: str, **kwargs):
        """Edit a file by replacing old_string with new_string.

        The path is resolved against the workspace first.
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

        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            if old_string not in content:
                return {
                    "success": False,
                    "error": f"The specified text was not found in {path}"
                }

            count = content.count(old_string)
            if count > 1:
                return {
                    "success": False,
                    "error": f"The old_string appears {count} times in the file. Must be unique for safety. Include surrounding lines (like the function definition or comments) in 'old_string' to make it unique."
                }

            # Backup
            backup_path = path + ".backup"
            shutil.copy2(path, backup_path)

            new_content = content.replace(old_string, new_string, 1)

            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            return {
                "success": True,
                "result": f"File edited successfully: {os.path.abspath(path)}",
                "metadata": {
                    "path": os.path.abspath(path),
                    "backup": backup_path,
                    "replacements": 1,
                    "old_length": len(old_string),
                    "new_length": len(new_string)
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to edit file: {str(e)}"
            }
