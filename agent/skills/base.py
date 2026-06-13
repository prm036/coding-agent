"""Base class and registry for skills.

Skills are higher-level, reusable workflows that combine multiple tool calls.
They are invoked by the user with a '/skillname' command.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class Skill(ABC):
    """Base class for all skills.
    
    A skill is a multi-step recipe that can be invoked by name.
    Unlike tools (single actions), skills orchestrate multiple tool calls
    to accomplish a higher-level task.
    """
    
    name: str = ""           # e.g., "commit"
    description: str = ""    # What the skill does
    trigger: str = ""        # e.g., "/commit"
    
    @abstractmethod
    def execute(self, agent, args: str = "") -> Dict[str, Any]:
        """Execute the skill.
        
        Args:
            agent: The CodingAgent instance (to access tools and LLM).
            args: Optional arguments passed after the trigger (e.g., "/commit fix bug").
        
        Returns:
            Dict with 'success', 'result', and optionally 'actions' (list of tool calls made).
        """
        pass
    
    def get_help(self) -> str:
        """Return help text for this skill."""
        return f"{self.trigger}: {self.description}"


class SkillRegistry:
    """Registry for managing available skills."""
    
    def __init__(self):
        self._skills: Dict[str, Skill] = {}
    
    def register(self, skill: Skill):
        """Register a skill."""
        self._skills[skill.trigger] = skill
        # Also register by name for convenience
        self._skills[skill.name] = skill
    
    def get(self, trigger: str) -> Optional[Skill]:
        """Get a skill by its trigger command."""
        return self._skills.get(trigger)
    
    def list_skills(self) -> List[Skill]:
        """List all registered skills (by trigger only, avoiding duplicates)."""
        seen = set()
        result = []
        for skill in self._skills.values():
            if skill.trigger not in seen:
                seen.add(skill.trigger)
                result.append(skill)
        return result
    
    def get_help_text(self) -> str:
        """Get formatted help text for all skills."""
        lines = ["Available skills:"]
        for skill in self.list_skills():
            lines.append(f"  {skill.trigger}: {skill.description}")
        return "\n".join(lines)
