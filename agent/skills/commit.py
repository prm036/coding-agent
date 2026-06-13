"""/commit skill: stage changed files, generate a commit message, and create a git commit."""
import os
from .base import Skill


class CommitSkill(Skill):
    """Stage changed files, generate a commit message from the diff, and create a git commit."""
    
    name = "commit"
    description = "Stage all changed files, generate a commit message from the diff, and create a git commit."
    trigger = "/commit"
    
    def execute(self, agent, args: str = "") -> dict:
        """Execute the commit skill.
        
        Steps:
        1. Get git status to see changed files
        2. Get git diff of staged + unstaged changes
        3. Use LLM to generate commit message from diff
        4. Stage all changes
        5. Create commit with generated message
        """
        actions = []
        cwd = str(agent.permissions.workspace) if hasattr(agent, "permissions") else "."
        
        # Step 1: Check git status
        status_result = agent.tools["git"].execute(command="status --short", cwd=cwd)
        actions.append({"tool": "git status", "result": status_result})
        
        if not status_result["success"]:
            return {
                "success": False,
                "error": f"Failed to check git status: {status_result.get('error', 'Unknown error')}",
                "actions": actions
            }
        
        if not status_result.get("result", "").strip() or status_result.get("result", "").strip() == "(no output)":
            return {
                "success": False,
                "error": "No changes to commit.",
                "actions": actions
            }
        
        # Step 2: Get diff
        diff_result = agent.tools["git"].execute(command="diff", cwd=cwd)
        actions.append({"tool": "git diff", "result": diff_result})
        
        diff_text = diff_result.get("result", "")
        if not diff_text or diff_text == "(no output)":
            # Maybe only staged changes
            diff_result = agent.tools["git"].execute(command="diff --staged", cwd=cwd)
            actions.append({"tool": "git diff --staged", "result": diff_result})
            diff_text = diff_result.get("result", "")
        
        # Step 3: Generate commit message using LLM
        system_prompt = """You are a helpful assistant that writes concise, conventional commit messages.
Follow the Conventional Commits format: type(scope): description
Types: feat, fix, docs, style, refactor, test, chore.
Write a single-line commit message (max 72 chars) that summarizes the changes.
Return ONLY the commit message, no quotes, no explanation."""

        user_prompt = f"""Here is the git status:\n{status_result.get('result', '')}\n\nHere is the git diff. Write a commit message:\n\n{diff_text[:3000]}"""
        
        commit_message = agent.llm.simple_chat(system_prompt, user_prompt).strip()
        # Clean up - remove quotes if present
        commit_message = commit_message.strip('"\'').split('\n')[0].strip()
        
        if args.strip():
            # User provided custom message
            commit_message = args.strip()
        
        print(f"\n[Commit Message] {commit_message}")
        
        # Step 4: Stage all changes
        add_result = agent.tools["git"].execute(command="add -A", cwd=cwd)
        actions.append({"tool": "git add -A", "result": add_result})
        
        # Step 5: Create commit
        # Escape quotes in commit message
        safe_message = commit_message.replace('"', '\\"')
        commit_result = agent.tools["git"].execute(
            command=f'commit -m "{safe_message}"',
            cwd=cwd
        )
        actions.append({"tool": f'git commit -m "{commit_message}"', "result": commit_result})
        
        if commit_result["success"]:
            return {
                "success": True,
                "result": f"Successfully committed: {commit_message}",
                "actions": actions
            }
        else:
            return {
                "success": False,
                "error": f"Failed to commit: {commit_result.get('error', commit_result.get('result', 'Unknown error'))}",
                "actions": actions
            }
