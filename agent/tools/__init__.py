from .file_read import FileReadTool
from .file_write import FileWriteTool, FileEditTool
from .shell import ShellExecuteTool
from .search import SearchTool
from .git_tool import GitTool
from .finish import FinishTaskTool

ALL_TOOLS = [
    FileReadTool(),
    FileWriteTool(),
    FileEditTool(),
    ShellExecuteTool(),
    SearchTool(),
    GitTool(),
    FinishTaskTool(),
]

def get_tool_map(permissions=None):
    """Build a name→tool mapping, optionally injecting the permission manager.

    When *permissions* is provided every tool that supports workspace
    sandboxing (``_permissions`` attribute) gets a reference so it can
    call ``permissions.resolve_path()`` before performing I/O.
    """
    tool_map = {}
    for tool in ALL_TOOLS:
        if permissions and hasattr(tool, '_permissions'):
            tool._permissions = permissions
        tool_map[tool.name] = tool
    return tool_map
