"""Agent loop: the main control flow that orchestrates the coding agent.

The loop follows the OODA pattern:
1. Observe: gather context (user message, tool results, file contents)
2. Think: send context to the LLM, which decides the next action
3. Act: execute the chosen tool or skill
4. Check: determine if the task is complete; if not, loop
"""
import json
import time
from typing import Dict, Any, List, Optional

from .tools import get_tool_map
from .skills import registry as skill_registry
from .permissions import PermissionManager
from .llm import LLMClient


# System prompt that defines the agent's behavior
SYSTEM_PROMPT = """You are an expert coding assistant with access to tools that let you interact with the filesystem, run shell commands, and search code.

Your goal is to help users with software engineering tasks by using the available tools effectively.

**Available Tools:**
- `file_read`: Read file contents. Always use this to examine files before modifying them.
- `file_write`: Write a complete file. Overwrites existing files! Use for creating new files.
- `file_edit`: Edit a file by replacing a specific string with another. Use for targeted changes.
- `shell_execute`: Run shell commands. Use for running tests, listing directories, checking git status.
- `search`: Search for files by name pattern or search file contents.
- `git`: Run git commands to inspect repository state.

**Rules:**
1. Always read files before editing them to understand the context.
2. Make minimal, focused changes. Prefer `file_edit` over `file_write` when modifying existing files.
3. After making changes, verify them (read the file back or run tests).
4. If a task requires multiple steps, break it down and execute one step at a time.
5. When done, summarize what you did and any important notes.
6. Do NOT make assumptions about file contents - always read first.
7. If you encounter errors, diagnose them and try to fix.
8. Use `search` to find relevant files in unfamiliar codebases.

**Skills** (invoke with /command):
- `/commit`: Stage and commit all changes with an auto-generated commit message
- `/test`: Run the project's test suite and report results
- `/review`: Review code changes for bugs and style issues

**Response Format:**
When you need to use a tool, respond with a JSON object inside ```json ... ``` blocks:
```json
{
    "thought": "Why I'm taking this action",
    "action": "tool_name",
    "arguments": {"param1": "value1"}
}
```

**CRITICAL INSTRUCTION: STOPPING**
When you have completed the user's task, you MUST STOP. Do not keep looking for things to do. Do not run random commands.
To stop and finish, call the `finish_task` tool with a summary of what you did.
"""


class CodingAgent:
    """The main coding agent that orchestrates tool use."""
    
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        permissions: Optional[PermissionManager] = None,
        max_iterations: int = 30,
        verbose: bool = False
    ):
        """Initialize the coding agent.
        
        Args:
            llm_client: LLM client for decision making.
            permissions: Permission manager for safety.
            max_iterations: Maximum loop iterations before giving up.
            verbose: Whether to print detailed logs.
        """
        self.llm = llm_client or LLMClient()
        self.permissions = permissions or PermissionManager()
        self.max_iterations = max_iterations
        self.verbose = verbose
        
        # Tool registry — inject permissions so tools can sandbox file paths
        self.tools = get_tool_map(permissions=self.permissions)
        
        # Skill registry
        self.skills = skill_registry
        
        # Conversation history
        self.messages: List[Dict[str, str]] = []
        
        # Action log for debugging
        self.action_log: List[Dict[str, Any]] = []
    
    def _log(self, message: str):
        """Print a log message if verbose mode is on."""
        if self.verbose:
            print(f"[AGENT] {message}")
    
    def _parse_response(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse the LLM response to extract tool calls or done signal."""
        import re
        import ast
        
        def _try_parse(text: str) -> Optional[Dict[str, Any]]:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                try:
                    # Fallback to ast.literal_eval for pseudo-JSON (e.g. using ''' or """)
                    result = ast.literal_eval(text)
                    if isinstance(result, dict):
                        return result
                except Exception:
                    pass
            return None

        # Look for JSON in code blocks
        json_blocks = re.findall(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        for block in json_blocks:
            parsed = _try_parse(block.strip())
            if parsed: return parsed
        
        # Try to find JSON in plain ``` blocks
        code_blocks = re.findall(r'```\s*(.*?)\s*```', content, re.DOTALL)
        for block in code_blocks:
            parsed = _try_parse(block.strip())
            if parsed: return parsed
        
        # Try the whole content as JSON
        return _try_parse(content.strip())
    
    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool with the given arguments."""
        if tool_name not in self.tools:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}. Available: {list(self.tools.keys())}"
            }
        
        tool = self.tools[tool_name]
        
        # Check permissions for dangerous tools
        if not self.permissions.request_approval(tool_name, arguments):
            return {
                "success": False,
                "error": f"User denied permission for {tool_name}"
            }
        
        try:
            self._log(f"Executing tool: {tool_name}({arguments})")
            result = tool.execute(**arguments)
            self._log(f"Tool result: success={result.get('success', False)}")
            return result
        except Exception as e:
            return {
                "success": False,
                "error": f"Error executing {tool_name}: {str(e)}. Check your arguments."
            }
    
    def _execute_skill(self, skill_trigger: str, args: str) -> Dict[str, Any]:
        """Execute a skill by its trigger command."""
        skill = self.skills.get(skill_trigger)
        if not skill:
            return {
                "success": False,
                "error": f"Unknown skill: {skill_trigger}. Available: {[s.trigger for s in self.skills.list_skills()]}"
            }
        
        self._log(f"Executing skill: {skill_trigger}({args})")
        result = skill.execute(self, args)
        self._log(f"Skill result: success={result.get('success', False)}")
        
        return result
    
    def run(self, user_task: str) -> str:
        """Run the agent loop on a user task.
        
        Args:
            user_task: The natural language task description.
        
        Returns:
            Summary of what the agent did.
        """
        print(f"\n{'='*70}")
        print(f"TASK: {user_task}")
        print(f"{'='*70}\n")
        
        # Initialize conversation
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_task}
        ]
        
        recent_action_signatures = []
        
        # Agent loop
        for iteration in range(self.max_iterations):
            print(f"\n--- Step {iteration + 1} ---")
            
            # 1. THINK: Send context to LLM
            tool_schemas = [tool.get_schema() for tool in self.tools.values()]
            
            try:
                response = self.llm.chat(self.messages, tools=tool_schemas)
                # -------------------------------------------------------------------
                # Compatibility shim: some LLMs (especially smaller local models) output
                # tool calls in a plain‑text style like:
                #   [LLM wants to call] tool_name({"arg": "value"})
                # The original parser only understood JSON‑encoded tool_calls.
                # If no structured tool_calls are present, we look for that pattern,
                # safely evaluate the argument dict, and synthesize a tool_calls list.
                # -------------------------------------------------------------------
                if not response.get("tool_calls"):
                    import re, ast
                    text = response.get("content", "")
                    pattern = re.compile(r"\[LLM wants to call\]\s*(\w+)\s*\((.*)\)")
                    match = pattern.search(text)
                    if match:
                        tool_name = match.group(1)
                        args_str = match.group(2).strip()
                        try:
                            # Use ast.literal_eval to safely parse Python literal dicts
                            args_dict = ast.literal_eval(args_str)
                        except Exception:
                            args_dict = {}
                        response["tool_calls"] = [{"name": tool_name, "arguments": args_dict, "id": "fallback-0"}]
            except Exception as e:
                error_msg = f"LLM API error: {str(e)}"
                print(f"[ERROR] {error_msg}")
                return error_msg
            
            # Check for API errors returned by the client
            if response.get("finish_reason") == "error":
                error_msg = response.get("error", "Unknown LLM API error")
                print(f"[ERROR] {error_msg}")
                print("Please check your API key, connection, and quota.")
                return f"Error: {error_msg}"
            
            # New guard for completely empty responses
            if not response.get("content") and not response.get("tool_calls"):
                print("[WARNING] Empty LLM response; stopping loop.")
                return "No response from LLM."
            
            content = response.get("content", "")
            
            # Log the LLM response
            self.action_log.append({
                "step": iteration + 1,
                "type": "llm_response",
                "content": content[:500] if content else "",
                "tool_calls": response.get("tool_calls", [])
            })
            
            # 2. Check for tool calls from the LLM
            if response.get("tool_calls"):
                for tc in response["tool_calls"]:
                    tool_name = tc["name"]
                    arguments = tc["arguments"]
                    # Ensure arguments is a dict; LLM may emit a string representation
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except Exception:
                            try:
                                import ast
                                arguments = ast.literal_eval(arguments)
                            except Exception:
                                arguments = {}

                    
                    print(f"\n[LLM wants to call] {tool_name}({arguments})")
                    
                    signature = json.dumps({"name": tool_name, "args": arguments}, sort_keys=True)
                    recent_action_signatures.append(signature)
                    
                    if recent_action_signatures[-8:].count(signature) >= 3:
                        error_msg = f"LOOP DETECTED: Agent repeated {tool_name} multiple times in a cycle. Stopping."
                        print(f"\n[!] {error_msg}")
                        return error_msg
                    
                    if tool_name == "finish_task":
                        summary = arguments.get("summary", "Task completed.")
                        print(f"\n{'='*70}")
                        print("TASK COMPLETE")
                        print(f"{'='*70}")
                        print(f"\n{summary}")
                        return summary
                    
                    # Execute the tool
                    result = self._execute_tool(tool_name, arguments)
                    
                    # Format result for the LLM
                    result_text = json.dumps(result, indent=2)
                    if len(result_text) > 2000:
                        result_text = result_text[:2000] + "\n... [truncated]"
                    
                    # Add tool result to conversation
                    self.messages.append({
                        "role": "assistant",
                        "content": f"I'll use the {tool_name} tool.",
                        "tool_calls": [{
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(arguments)
                            }
                        }]
                    })
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result_text + "\n\n[SYSTEM REMINDER]: If the user's task is fully complete, you MUST call the finish_task tool. Do not call any more tools."
                    })
                    
                    # Print result summary
                    if result.get("success"):
                        result_summary = result.get("result", "")[:200]
                        print(f"[Result] {result_summary}")
                    else:
                        print(f"[Error] {result.get('error', result.get('result', 'Unknown error'))}")
                
                continue  # Go to next iteration
            
            # 3. Check if the LLM is done
            parsed = self._parse_response(content)
            if parsed and parsed.get("done"):
                summary = parsed.get("summary", "Task completed.")
                print(f"\n{'='*70}")
                print("TASK COMPLETE")
                print(f"{'='*70}")
                print(f"\n{summary}")
                return summary
            
            # 4. Check if the LLM wants to use a tool via JSON in content
            if parsed and "action" in parsed:
                tool_name = parsed["action"]
                arguments = parsed.get("arguments", {})
                thought = parsed.get("thought", "")
                
                if thought:
                    print(f"[Thought] {thought}")
                print(f"\n[Action] {tool_name}({arguments})")
                
                signature = json.dumps({"name": tool_name, "args": arguments}, sort_keys=True)
                recent_action_signatures.append(signature)
                    
                if recent_action_signatures[-8:].count(signature) >= 3:
                    error_msg = f"LOOP DETECTED: Agent repeated {tool_name} multiple times in a cycle. Stopping."
                    print(f"\n[!] {error_msg}")
                    return error_msg
                elif tool_name == "finish_task":
                    summary = arguments.get("summary", "Task completed.")
                    print(f"\n{'='*70}")
                    print("TASK COMPLETE")
                    print(f"{'='*70}")
                    print(f"\n{summary}")
                    return summary
                elif tool_name.startswith('/'):
                    # The LLM is trying to call a skill
                    args_str = ""
                    if isinstance(arguments, dict):
                        # Extract the most likely argument values for skills
                        if "message" in arguments:
                            args_str = str(arguments["message"])
                        elif "target" in arguments:
                            args_str = str(arguments["target"])
                        else:
                            args_str = " ".join(str(v) for v in arguments.values())
                    elif isinstance(arguments, str):
                        args_str = arguments
                    
                    result = self._execute_skill(tool_name, args_str)
                else:
                    result = self._execute_tool(tool_name, arguments)
                
                result_text = json.dumps(result, indent=2)
                if len(result_text) > 2000:
                    result_text = result_text[:2000] + "\n... [truncated]"
                
                self.messages.append({
                    "role": "assistant",
                    "content": content
                })
                self.messages.append({
                    "role": "user",
                    "content": f"Tool result:\n{result_text}\n\n[SYSTEM REMINDER]: If the user's task is fully complete, you MUST call the finish_task tool. Do not call any more tools."
                })
                
                if result.get("success"):
                    result_summary = result.get("result", "")[:200]
                    print(f"[Result] {result_summary}")
                else:
                    print(f"[Error] {result.get('error', result.get('result', 'Unknown error'))}")
                
                continue
            
            # 5. Regular response - add to conversation and return
            if content.strip():
                print(f"\n[Agent] {content}")
                self.messages.append({
                    "role": "assistant",
                    "content": content
                })
                
                # Check if the task seems complete
                if any(phrase in content.lower() for phrase in [
                    "done", "complete", "finished", "i have", "i've completed",
                    "task is complete", "all done", "successfully"
                ]):
                    return content
            
            # Ask user if they want to continue
            try:
                user_input = input("\n[Press Enter to continue, or type feedback (or 'quit' to stop)]: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            
            if user_input.lower() in ('quit', 'exit', 'q'):
                break
            
            if user_input:
                self.messages.append({
                    "role": "user",
                    "content": user_input
                })
        
        else:
            print(f"\n[WARNING] Reached max iterations ({self.max_iterations}). Stopping.")
        
        # Print audit summary if verbose
        if self.verbose and hasattr(self.permissions, 'audit_log'):
            print(f"\n{self.permissions.get_audit_summary()}")
        
        # Collect summary from conversation
        return "Task ended. Check the conversation history for details."
    
    def run_interactive(self):
        """Run the agent in interactive mode."""
        print("""
╔══════════════════════════════════════════════════════════════════════╗
║                   LLM-Powered Coding Agent                           ║
║                                                                      ║
║  Type your task or question, and I'll use tools to help you.         ║
║                                                                      ║
║  Skills:                                                             ║
║    /commit [message]  - Stage and commit all changes                 ║
║    /test              - Run the test suite                           ║
║    /review [target]   - Review code changes                          ║
║                                                                      ║
║  Commands:                                                           ║
║    /help              - Show this help message                       ║
║    /tools             - List available tools                         ║
║    /quit              - Exit the agent                               ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
""")
        
        while True:
            try:
                user_input = input("\n🤖 You> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break
            
            if not user_input:
                continue
            
            if user_input.lower() in ('/quit', '/exit', 'quit', 'exit'):
                print("Goodbye!")
                break
            
            if user_input.lower() == '/help':
                print(self.skills.get_help_text())
                print("\n  /help   - Show this help")
                print("  /tools  - List available tools")
                print("  /quit   - Exit")
                continue
            
            if user_input.lower() == '/tools':
                for tool in self.tools.values():
                    print(f"  {tool.name}: {tool.description[:80]}")
                continue
            
            # Check for skill invocation
            if user_input.startswith('/'):
                parts = user_input.split(' ', 1)
                trigger = parts[0]
                args = parts[1] if len(parts) > 1 else ""
                
                result = self._execute_skill(trigger, args)
                if result.get("success"):
                    print(f"\n✅ {result['result']}")
                else:
                    print(f"\n❌ {result.get('error', result.get('result', 'Skill failed'))}")
                continue
            
            # Regular task - run the agent loop
            self.run(user_input)
