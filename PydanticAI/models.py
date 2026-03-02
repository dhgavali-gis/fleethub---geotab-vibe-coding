from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict

class TaskStep(BaseModel):
    tool_used: str = Field(..., description="The name of the tool that was used")
    summary: str = Field(..., description="A brief summary of what the tool returned or the action taken")
    tool_input: Optional[Dict[str, Any]] = Field(None, description="The input arguments passed to the tool")
    tool_output: Optional[str] = Field(None, description="The output from the tool")

class AgentResponse(BaseModel):
    final_answer: str = Field(..., description="The final natural language response to the user")
    steps_taken: List[TaskStep] = Field(default_factory=list, description="The sequence of steps/tools used to arrive at the answer")
    confidence_score: float = Field(..., ge=0, le=1, description="Confidence score between 0 and 1")
    map_commands: List[Dict[str, Any]] = Field(default_factory=list, description="List of map rendering commands generated during execution")
