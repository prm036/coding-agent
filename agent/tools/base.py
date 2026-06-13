"""Base class for all tools in the coding agent."""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class Tool(ABC):
    """Base class for all tools.
    
    Each tool has:
    - name: unique identifier
    - description: what the tool does
    - input_schema: JSON schema for the tool's arguments
    - danger_level: 'safe' or 'dangerous' (for permission system)
    """
    
    name: str = ""
    description: str = ""
    input_schema: Dict[str, Any] = {}
    danger_level: str = "safe"  # 'safe' or 'dangerous'
    
    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool with the given arguments.
        
        Returns a dict with at least a 'success' key and either
        'result' (on success) or 'error' (on failure).
        """
        pass
    
    def get_schema(self) -> Dict[str, Any]:
        """Return the tool's schema for LLM function calling."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            }
        }
