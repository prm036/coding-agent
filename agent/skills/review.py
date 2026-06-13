"""/review skill: read a code diff, analyze it for bugs and style issues, and produce a structured review."""
import os
from .base import Skill


class ReviewSkill(Skill):
    """Read a code diff, analyze it for bugs and style issues, and produce a structured review."""
    
    name = "review"
    description = "Review code changes (git diff) for bugs, style issues, and improvements. Usage: /review [filepath or 'staged']"
    trigger = "/review"
    
    def execute(self, agent, args: str = "") -> dict:
        """Execute the review skill.
        
        Steps:
        1. Get the diff to review (staged changes, unstaged, or from a file)
        2. Use LLM to analyze the code for issues
        3. Return structured review
        """
        actions = []
        cwd = str(agent.permissions.workspace) if hasattr(agent, "permissions") else "."
        
        # Step 1: Get the diff
        diff_text = ""
        
        if args.strip():
            arg = args.strip()
            if arg == "staged":
                diff_result = agent.tools["git"].execute(command="diff --staged", cwd=cwd)
                actions.append({"tool": "git diff --staged", "result": diff_result})
                diff_text = diff_result.get("result", "")
            elif os.path.isfile(arg):
                read_result = agent.tools["file_read"].execute(path=arg)
                actions.append({"tool": f"file_read: {arg}", "result": read_result})
                diff_text = read_result.get("result", "")
            else:
                diff_result = agent.tools["git"].execute(command=f"diff {arg}", cwd=cwd)
                actions.append({"tool": f"git diff {arg}", "result": diff_result})
                diff_text = diff_result.get("result", "")
        else:
            # Default: review unstaged changes
            diff_result = agent.tools["git"].execute(command="diff", cwd=cwd)
            actions.append({"tool": "git diff", "result": diff_result})
            diff_text = diff_result.get("result", "")
            
            if not diff_text or diff_text == "(no output)":
                # Try staged changes
                diff_result = agent.tools["git"].execute(command="diff --staged", cwd=cwd)
                actions.append({"tool": "git diff --staged", "result": diff_result})
                diff_text = diff_result.get("result", "")
                
            if not diff_text or diff_text == "(no output)":
                # Fallback to reviewing the last commit
                diff_result = agent.tools["git"].execute(command="show HEAD", cwd=cwd)
                actions.append({"tool": "git show HEAD", "result": diff_result})
                diff_text = diff_result.get("result", "")
        
        if not diff_text or diff_text == "(no output)":
            return {
                "success": False,
                "result": "No changes to review. The repository has no recent commits or uncommitted changes.",
                "actions": actions
            }
        
        # Step 2: Use LLM to analyze
        system_prompt = """You are an expert code reviewer. Analyze the provided code changes and produce a structured review.

Your review should include:
1. **Summary**: Brief overview of what the changes do (1-2 sentences).
2. **Issues**: List any bugs, logic errors, potential exceptions, or security concerns. Be specific about line numbers if possible.
3. **Style**: Note any style issues (naming, formatting, missing type hints, docstrings).
4. **Suggestions**: Recommend improvements for clarity, performance, or maintainability.
5. **Verdict**: APPROVE, REQUEST_CHANGES, or COMMENT.

Be thorough but concise. Focus on substantive issues over nitpicks."""

        user_prompt = f"Please review these code changes:\n\n```diff\n{diff_text[:5000]}\n```"
        
        review = agent.llm.simple_chat(system_prompt, user_prompt)
        
        return {
            "success": True,
            "result": review,
            "actions": actions,
            "metadata": {
                "diff_length": len(diff_text),
                "review_length": len(review)
            }
        }
