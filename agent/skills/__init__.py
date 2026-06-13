from .base import Skill, SkillRegistry
from .commit import CommitSkill
from .test import TestSkill
from .review import ReviewSkill

# Create global registry and register built-in skills
registry = SkillRegistry()
registry.register(CommitSkill())
registry.register(TestSkill())
registry.register(ReviewSkill())

__all__ = ['Skill', 'SkillRegistry', 'registry']
