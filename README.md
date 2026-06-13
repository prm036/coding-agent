# IEMS 490 - LLM-Powered Coding Agent

A modular, extensible coding agent that combines an LLM backbone with a tool harness to perform software engineering tasks like reading files, editing code, executing shell commands, and running tests.

## Features

- **Tool System**: File read/write/edit, shell execution, file/content search, git operations
- **Skill System**: Composable, higher-level workflows (`/commit`, `/test`, `/review`)
- **Agent Loop**: Multi-step reasoning with OODA cycle (Observe → Think → Act → Check)
- **Safety**: Permission system that requires confirmation before dangerous actions
- **Extensible**: Easy to add new tools and skills without modifying core code

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   User Input                         │
└───────────────────┬─────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────┐
│               Agent Loop (OODA)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ Observe  │─▶│  Think   │─▶│   Act    │          │
│  │          │  │  (LLM)   │  │ (Tools)  │          │
│  └──────────┘  └──────────┘  └────┬─────┘          │
│         ▲                         │                │
│         └──────── Check ◀─────────┘                │
└─────────────────────────────────────────────────────┘
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
┌─────────┐  ┌──────────┐  ┌────────────┐
│  Tools  │  │  Skills  │  │  Safety    │
│         │  │          │  │  (Perms)   │
│• read   │  │• commit │  │            │
│• write  │  │• test   │  │ Confirm    │
│• shell  │  │• review │  │ dangerous  │
│• search │  │          │  │ actions    │
│• git    │  │          │  │            │
└─────────┘  └──────────┘  └────────────┘
```

## Setup

### Prerequisites

- Python 3.8+
- Gemini API key

### Installation

```bash
# Clone or navigate to the project directory
cd coding-agent

# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set your API key
export GEMINI_API_KEY="your-api-key-here"
# Or create a .env file: echo 'GEMINI_API_KEY=your-key' > .env
```

### Dependencies

```
google-genai         # Google Gemini API client
openai               # OpenAI API client (for local models/vLLM/Ollama)
pyyaml>=6.0          # YAML parsing for skill configs
pathspec>=0.11.0     # File pattern matching
python-dotenv>=1.0.0 # Environment variable loading
```

## Usage

### Interactive Mode

Start the agent in interactive mode for a conversational experience:

```bash
python main.py
```

You'll see a prompt where you can type tasks:

```
🤖 You> Read the README and tell me what this project does
🤖 You> Find all Python files and list them
🤖 You> /test
🤖 You> /commit
```

### Single Task Mode

Run a single task directly:

```bash
python main.py "Find all TODO comments in the codebase"
python main.py "Read src/main.py and add docstrings to all functions"
python main.py "Run the tests and fix any failures"
```

### Command-Line Options

```bash
python main.py [task] [options]

Options:
  --model MODEL         LLM model (default: gemini-2.0-flash)
  --api-key KEY         API key (or set GEMINI_API_KEY env var)
  --base-url URL        Custom API base URL for OpenAI-compatible local models
  --auto-approve        Skip permission prompts (use with caution!)
  --verbose             Enable detailed logging
  --max-iterations N    Max agent loop iterations (default: 30)
  --help                Show full help

### Using Local Models (Ollama / vLLM)

You can run the agent completely free without API credits by using a local model server that is OpenAI-compatible (like Ollama).

1. Install [Ollama](https://ollama.com/)
2. Pull a coding-capable model, e.g., `ollama run qwen2.5-coder:7b` or `ollama run llama3.1`
3. Run the agent with the `--base-url` flag pointing to Ollama's local API:

```bash
python main.py --base-url http://localhost:11434/v1 --model qwen2.5-coder:7b "Find all TODOs in the codebase"
```
```



## Tools

The agent has access to the following tools:

### file_read
Read the contents of a file.
```json
{
  "action": "file_read",
  "arguments": {
    "path": "src/main.py",
    "offset": 1,
    "limit": 100
  }
}
```

### file_write
Create or overwrite a file with given content. **Dangerous** - requires confirmation.
```json
{
  "action": "file_write",
  "arguments": {
    "path": "src/new_file.py",
    "content": "print('hello')"
  }
}
```

### file_edit
Replace a specific string in a file. **Dangerous** - requires confirmation.
```json
{
  "action": "file_edit",
  "arguments": {
    "path": "src/main.py",
    "old_string": "def old_func():",
    "new_string": "def new_func():"
  }
}
```

### shell_execute
Run a shell command. **Dangerous** - requires confirmation.
```json
{
  "action": "shell_execute",
  "arguments": {
    "command": "ls -la",
    "cwd": ".",
    "timeout": 60
  }
}
```

### search
Search for files by name or search file contents.
```json
{
  "action": "search",
  "arguments": {
    "pattern": "*.py",
    "search_type": "filename",
    "path": "."
  }
}
```

### git
Execute git commands. **Dangerous** for write operations.
```json
{
  "action": "git",
  "arguments": {
    "command": "status",
    "cwd": "."
  }
}
```

## Skills

Skills are higher-level workflows invoked with `/` commands:

### /commit
Stage all changes, generate a commit message from the diff, and commit.
```bash
/commit                    # Auto-generate commit message
/commit "Fix login bug"    # Use custom message
```

### /test
Detect the test framework, run tests, and summarize results.
```bash
/test                      # Run all tests
```

### /review
Review code changes for bugs and style issues.
```bash
/review                    # Review unstaged/staged changes
/review staged             # Review staged changes only
/review myfile.py          # Review a specific file
```

## Safety and Permissions

The agent implements a **three-layer safety model**:

### Layer 1: Workspace Sandboxing

All file operations (`file_read`, `file_write`, `file_edit`, `search`) are sandboxed to the workspace directory. Paths are resolved against the workspace root using `PermissionManager.resolve_path()`. Any attempt to access files outside the workspace (e.g., `../../../etc/passwd` or `/etc/hosts`) is **blocked before any I/O occurs**.

```bash
# Restrict the agent to a specific directory
python main.py --workspace /path/to/project "Read all Python files"
```

### Layer 2: Danger Classification

Actions are classified as **safe** or **dangerous** based on the tool and its arguments:

| Classification | Tools | Details |
|---|---|---|
| **Safe** (no confirmation) | `file_read`, `search` | Read-only operations |
| **Always dangerous** | `file_write`, `file_edit` | Any write/edit requires confirmation |
| **Argument-dependent** | `shell_execute` | Safe prefixes (`ls`, `cat`, `grep`, `pytest`, etc.) pass through; everything else requires confirmation |
| **Argument-dependent** | `git` | Read-only commands (`status`, `diff`, `log`) are safe; mutating commands (`push`, `commit`, `reset --hard`) are dangerous |

Shell commands are also checked against **18 regex patterns** that catch destructive operations:
- `rm -rf`, `sudo`, `chmod`, `chown`, `mkfs`, `dd`, `kill`
- Pipe-to-shell attacks: `curl ... | sh`, `wget ... | bash`
- Package managers: `pip install`, `npm install`
- Destructive git: `git push`, `git commit`, `git reset --hard`

### Layer 3: User Confirmation

When a dangerous action is requested, you'll see:

```
============================================================
  ⚠️  PERMISSION REQUIRED
============================================================
  Tool: shell_execute
  Command: pip install requests
  ⚡ Matched dangerous pattern: \bpip\s+install\b
------------------------------------------------------------
  Options:
    [y] Yes  - approve this action
    [n] No   - deny this action
    [a] All  - approve all future uses of this tool (session)
    [q] Quit - exit the agent
============================================================
  Approve? [y/n/a/q]:
```

### Audit Logging

Every permission decision is timestamped and recorded in `PermissionManager.audit_log`. Use `--verbose` to print the full audit trail at the end of each task, or access `agent.permissions.audit_log` programmatically.

Use `--auto-approve` to skip confirmations (not recommended for production).

## Project Structure

```
coding-agent/
├── agent/
│   ├── __init__.py
│   ├── loop.py              # Main agent loop (OODA cycle)
│   ├── permissions.py       # Safety/permission system
│   ├── tools/               # Tool implementations
│   │   ├── __init__.py
│   │   ├── base.py          # Base tool class
│   │   ├── file_read.py
│   │   ├── file_write.py
│   │   ├── shell.py
│   │   ├── search.py
│   │   └── git_tool.py
│   ├── skills/              # Skill implementations
│   │   ├── __init__.py
│   │   ├── base.py          # Base skill class + registry
│   │   ├── commit.py
│   │   ├── test.py
│   │   └── review.py
│   └── llm/
│       ├── __init__.py
│       └── client.py        # LLM API client
├── main.py                  # Entry point
├── requirements.txt
├── .env                     # Environment variables (create this)
└── README.md
```

## Extending the Agent

### Adding a New Tool

1. Create a new file in `agent/tools/`:

```python
from .base import Tool

class MyTool(Tool):
    name = "my_tool"
    description = "What my tool does"
    danger_level = "safe"  # or "dangerous"
    input_schema = {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "Description"}
        },
        "required": ["param1"]
    }
    
    def execute(self, param1: str, **kwargs):
        # Your implementation
        return {"success": True, "result": f"Processed {param1}"}
```

2. Register it in `agent/tools/__init__.py`:

```python
from .my_tool import MyTool
ALL_TOOLS = [..., MyTool()]
```

### Adding a New Skill

1. Create a new file in `agent/skills/`:

```python
from .base import Skill

class MySkill(Skill):
    name = "my_skill"
    description = "What my skill does"
    trigger = "/mycommand"
    
    def execute(self, agent, args: str = "") -> dict:
        # Use agent.tools["tool_name"].execute(...)
        # Use agent.llm.simple_chat(system, user) for LLM calls
        return {
            "success": True,
            "result": "Done!",
            "actions": []
        }
```

2. Register it in `agent/skills/__init__.py`:

```python
from .my_skill import MySkill
registry.register(MySkill())
```

## Example Tasks

Here are some tasks you can try:

1. **Read and explain code**:
   ```
   "Read main.py and explain what this codebase does"
   ```

2. **Find TODOs**:
   ```
   "Find all TODO comments in this repository"
   ```

3. **Add type annotations**:
   ```
   "Read utils.py and add type annotations to all functions"
   ```

4. **Debug failing tests**:
   ```
   "The tests are failing. Read the test file and source code, find the bug, and fix it"
   ```

5. **Implement a feature**:
   ```
   "Create a new Python file that implements a Trie data structure with insert, search, and startsWith methods"
   ```

## Logging and Debugging

The agent logs all LLM calls and tool invocations. Use `--verbose` for detailed output:

```bash
python main.py --verbose "Your task"
```

You can also inspect the `agent.action_log` list programmatically for full execution traces.

## Limitations

- Requires API key for cloud LLM providers
- File operations are limited to the local filesystem
- Shell commands are sandboxed by the OS permissions
- LLM context window limits how much code can be processed at once
- Complex multi-file refactoring may require multiple iterations

## License

This project is for educational purposes (IEMS 490 - Foundations of Large Language Models).
