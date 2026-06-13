"""Tool for searching files by name or content."""
import os
import fnmatch
import re
from .base import Tool


class SearchTool(Tool):
    """Search for files by name pattern or search file contents by keyword."""
    
    name = "search"
    description = "Search for files by name pattern (e.g., '*.py') or search within file contents for a keyword. Use to find files, explore codebases, or locate specific functions/variables."
    danger_level = "safe"
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Filename pattern (e.g., '*.py', 'test_*.js') or regular expression for content search (e.g., 'TODO|FIXME')."
            },
            "path": {
                "type": "string",
                "description": "Directory to search in. Default: current directory.",
                "default": "."
            },
            "search_type": {
                "type": "string",
                "description": "'filename' to search by filename pattern, 'content' to search within file contents.",
                "enum": ["filename", "content"]
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return. Default: 20.",
                "default": 20
            }
        },
        "required": ["pattern", "search_type"]
    }
    
    # Common directories to skip
    SKIP_DIRS = {'.git', '__pycache__', '.pytest_cache', 'node_modules', '.venv', 'venv', '.tox', '.egg-info', 'build', 'dist'}

    # Reference to the permission manager, injected at registration time
    _permissions = None

    def execute(self, pattern: str, search_type: str, path: str = ".", max_results: int = 20, **kwargs):
        """Search for files or content."""
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
                "error": f"Path not found: {path}"
            }
        
        try:
            if search_type == "filename":
                results = self._search_by_filename(pattern, path, max_results)
            elif search_type == "content":
                results = self._search_by_content(pattern, path, max_results)
            else:
                return {
                    "success": False,
                    "error": f"Unknown search_type: {search_type}. Use 'filename' or 'content'."
                }
            
            return {
                "success": True,
                "result": f"Found {len(results)} result(s)",
                "matches": results,
                "metadata": {
                    "pattern": pattern,
                    "search_type": search_type,
                    "path": os.path.abspath(path),
                    "total_found": len(results)
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Search failed: {str(e)}"
            }
    
    def _search_by_filename(self, pattern, root_path, max_results):
        """Find files matching a filename pattern."""
        results = []
        for dirpath, dirnames, filenames in os.walk(root_path):
            # Skip hidden/special directories
            dirnames[:] = [d for d in dirnames if d not in self.SKIP_DIRS and not d.startswith('.')]
            
            for filename in filenames:
                if fnmatch.fnmatch(filename, pattern):
                    full_path = os.path.join(dirpath, filename)
                    results.append(full_path)
                    if len(results) >= max_results:
                        return results
        return results
    
    def _search_by_content(self, keyword, root_path, max_results):
        """Find files containing a keyword (supports regex)."""
        import re
        try:
            pattern = re.compile(keyword)
        except re.error:
            # Fallback to literal if invalid regex
            pattern = re.compile(re.escape(keyword))
            
        results = []
        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if d not in self.SKIP_DIRS and not d.startswith('.')]
            
            for filename in filenames:
                # Skip binary files by extension
                if any(filename.endswith(ext) for ext in ['.pyc', '.so', '.dll', '.exe', '.png', '.jpg', '.gif', '.zip', '.tar.gz']):
                    continue
                
                full_path = os.path.join(dirpath, filename)
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    if pattern.search(content):
                        # Find line numbers
                        lines = content.split('\n')
                        matching_lines = []
                        for i, line in enumerate(lines, 1):
                            if pattern.search(line):
                                matching_lines.append(f"  Line {i}: {line.strip()[:100]}")
                                if len(matching_lines) >= 3:  # Limit lines per file
                                    matching_lines.append("  ...")
                                    break
                        
                        results.append({
                            "file": full_path,
                            "matches": matching_lines
                        })
                        if len(results) >= max_results:
                            return results
                except (IOError, OSError, UnicodeDecodeError):
                    continue
        return results
