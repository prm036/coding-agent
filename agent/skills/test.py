"""/test skill: detect the project's test framework, run the test suite, and summarize failures."""
import os
from .base import Skill


class TestSkill(Skill):
    """Detect the project's test framework, run tests, and summarize results."""
    
    name = "test"
    description = "Detect the project's test framework, run the test suite, and summarize failures."
    trigger = "/test"
    
    # Priority order for test detection
    TEST_COMMANDS = [
        # Python
        ("pytest", "pytest -v"),
        ("unittest", "python -m unittest discover -v"),
        ("setup.py", "python setup.py test"),
        # JavaScript/TypeScript
        ("jest", "npx jest"),
        ("mocha", "npx mocha"),
        ("vitest", "npx vitest run"),
        # Generic package.json
        ("npm", "npm test"),
        # Makefile
        ("makefile", "make test"),
    ]
    
    def execute(self, agent, args: str = "") -> dict:
        """Execute the test skill.
        
        Steps:
        1. Detect test framework by examining project files
        2. Run the appropriate test command
        3. Summarize results using LLM if needed
        """
        actions = []
        cwd = str(agent.permissions.workspace) if hasattr(agent, "permissions") else "."
        
        # Step 1: Detect test framework
        detected = None
        
        # Check for common test config files
        checks = [
            ("pytest.ini", "pytest"),
            ("setup.cfg", "pytest"),
            ("pyproject.toml", "pytest"),
            ("jest.config.js", "jest"),
            ("jest.config.ts", "jest"),
            ("vitest.config.ts", "vitest"),
            ("package.json", "npm"),
            ("Makefile", "makefile"),
        ]
        
        for filename, framework in checks:
            if os.path.exists(os.path.join(cwd, filename)):
                # For package.json, check if it has a test script
                if filename == "package.json":
                    read_result = agent.tools["file_read"].execute(path="package.json")
                    if read_result["success"] and '"test"' in read_result["result"]:
                        detected = (framework, self._get_command(framework))
                        break
                else:
                    detected = (framework, self._get_command(framework))
                    break
        
        # Check for test directories
        if not detected:
            for dirname in ["tests", "test", "__tests__", "spec"]:
                if os.path.isdir(os.path.join(cwd, dirname)):
                    # Check for Python test files
                    for fname in os.listdir(os.path.join(cwd, dirname)):
                        if fname.startswith("test_") and fname.endswith(".py"):
                            detected = ("unittest", "python -m unittest discover -v")
                            break
                        if fname.endswith(".test.js") or fname.endswith(".spec.js"):
                            detected = ("jest", "npx jest")
                            break
                    if detected:
                        break
        
        # Check for test files directly in the root directory
        if not detected:
            for fname in os.listdir(cwd):
                if os.path.isfile(os.path.join(cwd, fname)):
                    if fname.startswith("test_") and fname.endswith(".py"):
                        detected = ("unittest", "python -m unittest discover -v")
                        break
                    if fname.endswith(".test.js") or fname.endswith(".spec.js"):
                        detected = ("jest", "npx jest")
                        break
        
        if not detected:
            return {
                "success": False,
                "error": "Could not detect a test framework. Supported: pytest, jest, vitest, npm test, make test.",
                "actions": actions
            }
        
        framework, command = detected
        print(f"[TestSkill] Detected test framework: {framework}")
        print(f"[TestSkill] Running: {command}")
        
        # Step 2: Run tests
        test_result = agent.tools["shell_execute"].execute(command=command, cwd=cwd, timeout=120)
        actions.append({"tool": f"shell_execute: {command}", "result": test_result})
        
        output = test_result.get("result", "")
        exit_code = test_result["metadata"].get("exit_code", -1)
        
        # Step 3: Summarize with LLM if there are failures
        summary = output
        if exit_code != 0 and len(output) > 500:
            # Use LLM to summarize failures
            system_prompt = """You are a test output analyzer. Summarize the test failures concisely.
List each failed test with the error message. Keep it under 300 words."""
            summary = agent.llm.simple_chat(system_prompt, f"Summarize these test failures:\n\n{output[:4000]}")
        
        success = exit_code == 0
        return {
            "success": success,
            "result": f"Tests {'passed' if success else 'failed'} (exit code {exit_code})\n\n{summary}",
            "actions": actions,
            "metadata": {
                "framework": framework,
                "command": command,
                "exit_code": exit_code
            }
        }
    
    def _get_command(self, framework: str) -> str:
        """Get the test command for a framework."""
        for name, cmd in self.TEST_COMMANDS:
            if name == framework:
                return cmd
        return "echo 'Unknown test framework'"
