import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from agent.models.llm_interface import LocalLLM

logger = logging.getLogger(__name__)

@dataclass
class PlanStep:
    step_id: str
    description: str
    tool_name: str
    tool_params: Dict[str, Any]
    depends_on: List[str] = field(default_factory=list)
    requires_confirmation: bool = False

@dataclass
class ExecutionPlan:
    goal: str
    steps: List[PlanStep]
    estimated_duration: str = "Unknown"
    risks: List[str] = field(default_factory=list)

class Planner:
    """Uses LLM to break goals into ordered steps."""
    
    def __init__(self, llm: LocalLLM):
        self.llm = llm
        
    def create_plan(self, goal: str, available_tools: List[Dict[str, Any]], context: Dict[str, Any]) -> ExecutionPlan:
        """Creates an initial plan to achieve a goal."""
        
        schema = {
            "goal_understanding": "string",
            "estimated_duration": "string",
            "risks": ["string"],
            "steps": [
                {
                    "step_id": "string",
                    "description": "string",
                    "tool_name": "string",
                    "tool_params": "object",
                    "depends_on": ["string"]
                }
            ]
        }
        
        # We only pass tool names and descriptions to save context window
        tools_summary = [{"name": t["function"]["name"], "desc": t["function"]["description"]} for t in available_tools]
        
        prompt = f"Create a step-by-step plan to achieve this goal: '{goal}'.\nAvailable tools: {json.dumps(tools_summary)}\nContext: {json.dumps(context)}"
        
        try:
            plan_data = self.llm.generate_structured(prompt, schema)
            
            steps = []
            for s_data in plan_data.get("steps", []):
                steps.append(PlanStep(
                    step_id=s_data.get("step_id", "unknown"),
                    description=s_data.get("description", ""),
                    tool_name=s_data.get("tool_name", ""),
                    tool_params=s_data.get("tool_params", {}),
                    depends_on=s_data.get("depends_on", []),
                    requires_confirmation=False # Usually determined by tool registry later
                ))
                
            return ExecutionPlan(
                goal=goal,
                steps=steps,
                estimated_duration=plan_data.get("estimated_duration", "Unknown"),
                risks=plan_data.get("risks", [])
            )
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            # Return empty plan on failure
            return ExecutionPlan(goal=goal, steps=[])
            
    def replan(self, original_plan: ExecutionPlan, failed_step_id: str, error_msg: str, history: List[Any]) -> ExecutionPlan:
        """Adapts plan when a step fails."""
        # For simplicity in this implementation, we just drop the failed step and its dependents
        # In a real AIOS, the LLM would be asked to generate an alternative sub-plan
        
        failed_and_dependents = {failed_step_id}
        
        # Iteratively find all steps that depend on the failed one
        added_new = True
        while added_new:
            added_new = False
            for step in original_plan.steps:
                if step.step_id not in failed_and_dependents:
                    if any(dep in failed_and_dependents for dep in step.depends_on):
                        failed_and_dependents.add(step.step_id)
                        added_new = True
                        
        remaining_steps = [s for s in original_plan.steps if s.step_id not in failed_and_dependents]
        
        # We should really call the LLM here to figure out the fix, but we'll mock it for now
        return ExecutionPlan(
            goal=original_plan.goal,
            steps=remaining_steps,
            estimated_duration="Updated",
            risks=original_plan.risks + [f"Recovery from {failed_step_id} failure"]
        )
