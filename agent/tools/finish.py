from typing import Dict, Any
from .base import Tool

class FinishTaskTool(Tool):
    """Tool to call when the task is complete."""
    
    name = "finish_task"
    description = "Call this tool when you have completed the user's request."
    input_schema = {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Detailed summary of what was accomplished."
            }
        },
        "required": ["summary"]
    }
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        return {
            "success": True,
            "result": kwargs.get("summary", "Task complete.")
        }
