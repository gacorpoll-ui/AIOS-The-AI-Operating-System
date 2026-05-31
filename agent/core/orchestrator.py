import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from agent.models.llm_interface import LocalLLM
from agent.core.tool_registry import ToolRegistry, ToolResult
from agent.core.memory import MemoryEngine
from .planner import Planner, ExecutionPlan, PlanStep
from .executor import ParallelExecutor, StepResult

logger = logging.getLogger(__name__)

@dataclass
class ErrorAction:
    action: str  # RETRY, SKIP, ABORT, REPLAN
    reason: str

@dataclass
class ReflectionResult:
    goal_achieved: bool
    progress_summary: str
    next_actions: List[str]
    blockers: List[str]

@dataclass
class AgentResult:
    success: bool
    final_message: str
    execution_history: List[StepResult]
    iterations: int

class AgentOrchestrator:
    """Handles complex multi-step goals autonomously."""
    
    def __init__(self, llm: LocalLLM, tools: ToolRegistry, memory: MemoryEngine, planner: Planner):
        self.llm = llm
        self.tools = tools
        self.memory = memory
        self.planner = planner
        self.executor = ParallelExecutor(tools)
        self.max_iterations = 20
        
    def run(self, goal: str, context: Optional[Dict[str, Any]] = None, on_progress: callable = None) -> AgentResult:
        """Main agentic loop: Plan -> Execute -> Observe -> Reflect -> Repeat."""
        if not context:
            context = {}
            
        iterations = 0
        execution_history: List[StepResult] = []
        
        # 1. Initial Plan
        if on_progress: on_progress(f"Planning how to achieve: '{goal}'")
        current_plan = self._plan(goal, context)
        
        while iterations < self.max_iterations:
            iterations += 1
            if on_progress: on_progress(f"Iteration {iterations}/{self.max_iterations}")
            
            # 2. Execute pending steps
            pending_steps = [s for s in current_plan.steps if s.step_id not in [h.step_id for h in execution_history]]
            
            if not pending_steps:
                if on_progress: on_progress("No pending steps. Checking completion...")
            else:
                # We execute one unblocked layer at a time in the real system,
                # but for simplicity we'll let the ParallelExecutor handle dependencies
                if on_progress: on_progress(f"Executing {len(pending_steps)} steps...")
                
                def step_callback(res: StepResult):
                    if on_progress:
                        status = "✅" if res.success else "❌"
                        on_progress(f"  {status} Step {res.step_id}: {res.output if res.success else res.error}")
                
                batch_results = self.executor.execute_plan(current_plan, execution_history, step_callback)
                execution_history.extend(batch_results)
                
                # Handle errors
                failed_steps = [r for r in batch_results if not r.success]
                if failed_steps:
                    for failed in failed_steps:
                        action = self._handle_error(
                            next((s for s in current_plan.steps if s.step_id == failed.step_id), None),
                            Exception(failed.error)
                        )
                        
                        if action.action == "ABORT":
                            return AgentResult(False, f"Aborted due to unrecoverable error: {failed.error}", execution_history, iterations)
                        elif action.action == "REPLAN":
                            if on_progress: on_progress(f"Replanning due to error in step {failed.step_id}...")
                            current_plan = self.planner.replan(current_plan, failed.step_id, failed.error, execution_history)
                            break # Break the error loop and start next iteration with new plan
                            
                    if any(a.action == "REPLAN" for a in [action]):
                        continue # Skip reflection this round, go straight to executing new plan
            
            # 3. Observe & Reflect
            if on_progress: on_progress("Reflecting on progress...")
            reflection = self._reflect(execution_history, goal)
            
            if reflection.goal_achieved:
                return AgentResult(
                    success=True, 
                    final_message=reflection.progress_summary, 
                    execution_history=execution_history, 
                    iterations=iterations
                )
                
            if reflection.blockers and not pending_steps:
                # Stuck
                return AgentResult(
                    success=False,
                    final_message=f"Agent got stuck. Blockers: {', '.join(reflection.blockers)}",
                    execution_history=execution_history,
                    iterations=iterations
                )
                
            # If not achieved and no pending steps, we need a new plan
            if not pending_steps:
                if on_progress: on_progress("Creating follow-up plan based on reflection...")
                context["previous_history"] = [{"step_id": r.step_id, "success": r.success} for r in execution_history]
                current_plan = self._plan(goal + f" (Focus on: {', '.join(reflection.next_actions)})", context)
                
        # Hit max iterations
        return AgentResult(
            success=False,
            final_message=f"Reached maximum iterations ({self.max_iterations}) without achieving goal.",
            execution_history=execution_history,
            iterations=iterations
        )
        
    def _plan(self, goal: str, context: Dict[str, Any]) -> ExecutionPlan:
        """Delegates to Planner to create execution plan."""
        available_tools = self.tools.list_tools()
        return self.planner.create_plan(goal, available_tools, context)
        
    def _reflect(self, steps_so_far: List[StepResult], goal: str) -> ReflectionResult:
        """LLM assesses if goal is achieved and what's next."""
        if not steps_so_far:
            return ReflectionResult(False, "No steps executed yet.", ["Start execution"], [])
            
        history_str = json.dumps([
            {"id": s.step_id, "success": s.success, "output": str(s.output)[:200] if s.success else str(s.error)}
            for s in steps_so_far
        ])
        
        schema = {
            "goal_achieved": "boolean",
            "progress_summary": "string",
            "next_actions": ["string"],
            "blockers": ["string"]
        }
        
        prompt = f"Goal: {goal}\nExecution History: {history_str}\nAssess the current state against the goal."
        
        try:
            res = self.llm.generate_structured(prompt, schema)
            return ReflectionResult(
                goal_achieved=res.get("goal_achieved", False),
                progress_summary=res.get("progress_summary", "Reflection failed."),
                next_actions=res.get("next_actions", []),
                blockers=res.get("blockers", [])
            )
        except Exception:
            # Fallback reflection
            all_success = all(s.success for s in steps_so_far)
            return ReflectionResult(all_success, f"Executed {len(steps_so_far)} steps.", [], [])
            
    def _handle_error(self, step: Optional[PlanStep], error: Exception) -> ErrorAction:
        """Decide how to handle an error."""
        # Simplified heuristic - in reality we might ask LLM
        err_str = str(error).lower()
        if "timeout" in err_str:
            return ErrorAction("RETRY", "Command timed out")
        elif "permission" in err_str or "not found" in err_str:
            return ErrorAction("REPLAN", "Need alternative approach due to system constraints")
        elif "aborted by user" in err_str:
            return ErrorAction("ABORT", "User cancelled")
        else:
            return ErrorAction("REPLAN", "Unknown error requires new strategy")
