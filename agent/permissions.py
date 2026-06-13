"""Safety and permission system for the coding agent.

The permission model has three layers:
1. **Workspace sandboxing**: All file paths are resolved against the workspace
   root. Attempts to access paths outside the workspace (e.g. ../../../etc/passwd)
   are blocked before any I/O occurs.
2. **Danger classification**: Actions are classified as safe or dangerous based on
   the tool name and its arguments. Dangerous actions require user confirmation.
3. **Audit logging**: Every permission decision is recorded so the operator can
   review what the agent was allowed (or denied) to do.
"""
import os
import re
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List


# ────────────────────────────────────────────────────────────────────────────
# Regex patterns that flag a shell command as dangerous
# ────────────────────────────────────────────────────────────────────────────
DANGEROUS_SHELL_PATTERNS = [
    r"\brm\s+(-\w*[rRf])",         # rm with recursive/force flags
    r"\brmdir\b",                   # remove directory
    r"\bsudo\b",                    # privilege escalation
    r"\bchmod\b",                   # permission changes
    r"\bchown\b",                   # ownership changes
    r"\bcurl\b.*\|\s*(sh|bash)",    # pipe-to-shell from curl
    r"\bwget\b.*\|\s*(sh|bash)",    # pipe-to-shell from wget
    r">\s*/dev/",                   # overwrite device nodes
    r"\bdd\b\s+if=",               # raw disk write
    r"\bmkfs\b",                    # filesystem format
    r"\bkill\b",                    # kill processes
    r"\bpkill\b",                   # kill processes by name
    r"\bgit\s+push\b",             # push to remote
    r"\bgit\s+commit\b",           # create commit
    r"\bgit\s+reset\s+--hard\b",   # destructive git reset
    r"\bpip\s+install\b",          # install packages
    r"\bnpm\s+install\b",          # install packages
    r"\bmv\s+/",                   # move from root paths
    r":\(\)\{.*\}",                # fork bomb
]


class PermissionDecision:
    """Immutable record of a single permission decision.

    Stored in the audit log so every action the agent took (or was denied)
    can be reviewed after the session.
    """

    def __init__(self, tool_name: str, arguments: Dict[str, Any],
                 dangerous: bool, allowed: bool, reason: str):
        self.timestamp = datetime.datetime.now().isoformat()
        self.tool_name = tool_name
        self.arguments = arguments
        self.dangerous = dangerous
        self.allowed = allowed
        self.reason = reason

    def __repr__(self):
        status = "ALLOWED" if self.allowed else "DENIED"
        return f"[{self.timestamp}] {status} {self.tool_name}: {self.reason}"


class PermissionManager:
    """Manages workspace sandboxing, danger classification, and user approval.

    Key safety properties:
    - ``resolve_path`` ensures every file operation stays inside the workspace.
    - ``classify_shell`` uses regex patterns to flag destructive commands.
    - ``request_approval`` gates dangerous actions behind user confirmation
      with options for one-time, per-tool-session, or auto-approve modes.
    """

    # Tools that never need confirmation
    SAFE_TOOLS = {"file_read", "search"}
    # Tools that always (or conditionally) need confirmation
    DANGEROUS_TOOLS = {"file_write", "file_edit", "shell_execute", "git"}

    def __init__(self, workspace: Optional[str] = None,
                 auto_approve: bool = False):
        """Initialize the permission manager.

        Args:
            workspace: Root directory the agent is allowed to access.
                       Defaults to the current working directory.
            auto_approve: If True, skip confirmation for dangerous actions
                          (use only for testing / demos!).
        """
        self.workspace = Path(workspace or os.getcwd()).resolve()
        self.auto_approve = auto_approve
        self._session_approvals: set = set()  # Tools approved for this session
        self.audit_log: List[PermissionDecision] = []

    # ────────────────────────────────────────────────────────────────────
    # Workspace sandboxing
    # ────────────────────────────────────────────────────────────────────

    def resolve_path(self, path: str) -> str:
        """Resolve *path* relative to the workspace and verify it stays inside.

        If *path* is relative it is resolved against ``self.workspace``.
        If it is absolute it is used as-is but must still fall within the
        workspace tree.

        Returns:
            The resolved absolute path as a string.

        Raises:
            PermissionError: If the resolved path escapes the workspace.
        """
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.workspace / candidate
        candidate = candidate.resolve()

        # Allow the workspace root itself and anything underneath it
        if candidate != self.workspace and self.workspace not in candidate.parents:
            raise PermissionError(
                f"Path escapes workspace: '{path}' resolves to "
                f"'{candidate}' which is outside '{self.workspace}'"
            )
        return str(candidate)

    # ────────────────────────────────────────────────────────────────────
    # Danger classification
    # ────────────────────────────────────────────────────────────────────

    def is_dangerous(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """Classify whether a tool call is potentially dangerous.

        Safe calls proceed without user confirmation. Dangerous calls must
        go through ``request_approval``.
        """
        if tool_name in self.SAFE_TOOLS:
            return False

        if tool_name in ("file_write", "file_edit"):
            return True

        if tool_name == "shell_execute":
            return self.classify_shell(arguments.get("command", ""))

        if tool_name == "git":
            return self._classify_git(arguments.get("command", ""))

        # Unknown tools default to dangerous
        return True

    def classify_shell(self, command: str) -> bool:
        """Return True if *command* matches any dangerous shell pattern.

        Also returns True for any command not matching a known-safe prefix,
        so the default posture is cautious.
        """
        # First: check regex blocklist
        for pattern in DANGEROUS_SHELL_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return True

        # Second: whitelist well-known read-only commands
        safe_prefixes = (
            "ls", "cat", "echo", "pwd", "find", "grep", "head", "tail",
            "wc", "which", "env", "printenv", "date", "uname", "whoami",
            "python -c", "python3 -c", "python -m pytest", "python3 -m pytest",
            "pytest",
        )
        stripped = command.strip()
        if stripped.startswith(safe_prefixes):
            return False

        # Default: treat unknown commands as dangerous
        return True

    def _classify_git(self, command: str) -> bool:
        """Return True if *command* is a mutating git subcommand."""
        safe_git_commands = (
            "status", "diff", "log", "show", "branch", "remote -v",
            "remote", "tag", "stash list", "blame",
        )
        stripped = command.strip()
        if stripped.startswith(safe_git_commands):
            return False
        return True

    # ────────────────────────────────────────────────────────────────────
    # Approval gate
    # ────────────────────────────────────────────────────────────────────

    def request_approval(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """Gate a tool call behind user approval if it is dangerous.

        Returns True if the call is allowed, False if denied.
        Every decision is appended to ``self.audit_log``.
        """
        dangerous = self.is_dangerous(tool_name, arguments)

        if not dangerous:
            self._log_decision(tool_name, arguments, dangerous=False,
                               allowed=True, reason="safe action")
            return True

        if self.auto_approve:
            self._log_decision(tool_name, arguments, dangerous=True,
                               allowed=True, reason="auto-approved")
            return True

        if tool_name in self._session_approvals:
            self._log_decision(tool_name, arguments, dangerous=True,
                               allowed=True, reason="session-approved")
            return True

        # ── Interactive confirmation ──────────────────────────────────
        print("\n" + "=" * 60)
        print("  ⚠️  PERMISSION REQUIRED")
        print("=" * 60)
        print(f"  Tool: {tool_name}")

        if tool_name == "file_write":
            print(f"  File: {arguments.get('path', 'unknown')}")
            content = arguments.get('content', '')
            print(f"  Content length: {len(content)} chars")
        elif tool_name == "file_edit":
            print(f"  File: {arguments.get('path', 'unknown')}")
            old_str = arguments.get('old_string', '')
            print(f"  Replacing: {old_str[:60]}{'...' if len(old_str) > 60 else ''}")
        elif tool_name == "shell_execute":
            cmd = arguments.get('command', 'unknown')
            print(f"  Command: {cmd}")
            # Show which pattern matched, if any
            for pattern in DANGEROUS_SHELL_PATTERNS:
                if re.search(pattern, cmd, re.IGNORECASE):
                    print(f"  ⚡ Matched dangerous pattern: {pattern}")
                    break
        elif tool_name == "git":
            print(f"  Git: {arguments.get('command', 'unknown')}")

        print("-" * 60)
        print("  Options:")
        print("    [y] Yes  - approve this action")
        print("    [n] No   - deny this action")
        print("    [a] All  - approve all future uses of this tool (session)")
        print("    [q] Quit - exit the agent")
        print("=" * 60)

        while True:
            try:
                choice = input("  Approve? [y/n/a/q]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n  Denied (input closed).")
                self._log_decision(tool_name, arguments, dangerous=True,
                                   allowed=False, reason="input closed")
                return False

            if choice == 'y':
                self._log_decision(tool_name, arguments, dangerous=True,
                                   allowed=True, reason="user approved")
                return True
            elif choice == 'n':
                print("  Action denied.")
                self._log_decision(tool_name, arguments, dangerous=True,
                                   allowed=False, reason="user denied")
                return False
            elif choice == 'a':
                self._session_approvals.add(tool_name)
                print(f"  Approved all future {tool_name} calls this session.")
                self._log_decision(tool_name, arguments, dangerous=True,
                                   allowed=True,
                                   reason="user approved (session-wide)")
                return True
            elif choice == 'q':
                print("  Exiting agent.")
                self._log_decision(tool_name, arguments, dangerous=True,
                                   allowed=False, reason="user quit")
                raise SystemExit(0)
            else:
                print("  Please enter y, n, a, or q.")

    # ────────────────────────────────────────────────────────────────────
    # Audit log helpers
    # ────────────────────────────────────────────────────────────────────

    def _log_decision(self, tool_name: str, arguments: Dict[str, Any],
                      dangerous: bool, allowed: bool, reason: str):
        """Append a PermissionDecision to the audit log."""
        self.audit_log.append(PermissionDecision(
            tool_name=tool_name,
            arguments=arguments,
            dangerous=dangerous,
            allowed=allowed,
            reason=reason,
        ))

    def get_audit_summary(self) -> str:
        """Return a human-readable summary of the audit log."""
        if not self.audit_log:
            return "No actions recorded."
        lines = [f"Audit log ({len(self.audit_log)} entries):"]
        for entry in self.audit_log:
            lines.append(f"  {entry}")
        return "\n".join(lines)
