import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Set, Callable

from agent.core.tool_registry import ToolRegistry
from .planner import ExecutionPlan, PlanStep

logger = logging.getLogger(__name__)

@dataclass
class StepResult:
    step_id: str
    success: bool
    output: Any
    error: Optional[str]
    duration_ms: int

class ParallelExecutor:
    """Executes plan steps, respecting dependencies and using parallelism where possible."""
    
    def __init__(self, tools: ToolRegistry, max_workers: int = 4):
        self.tools = tools
        self.max_workers = max_workers
        
    def _get_executable_steps(self, plan: ExecutionPlan, completed_step_ids: Set[str], currently_running: Set[str]) -> List[PlanStep]:
        """Finds steps that have all dependencies met and aren't already completed or running."""
        executable = []
        for step in plan.steps:
            if step.step_id in completed_step_ids or step.step_id in currently_running:
                continue
                
            # Check if all dependencies are met
            deps_met = all(dep in completed_step_ids for dep in step.depends_on)
            if deps_met:
                executable.append(step)
                
        return executable
        
    def _execute_single_step(self, step: PlanStep) -> StepResult:
        """Executes a single step using the tool registry."""
        start_time = time.time()
        
        try:
            # For this MVP, we assume all actions are pre-confirmed or don't need it
            # In a real system, requires_confirmation would pause this thread and prompt the user
            tool_res = self.tools.execute(step.tool_name, step.tool_params, confirmed=True)
            
            return StepResult(
                step_id=step.step_id,
                success=tool_res.success,
                output=tool_res.output,
                error=tool_res.error,
                duration_ms=tool_res.execution_time_ms
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return StepResult(
                step_id=step.step_id,
                success=False,
                output=None,
                error=str(e),
                duration_ms=duration_ms
            )

    def execute_plan(self, plan: ExecutionPlan, previous_history: List[StepResult], on_step_complete: Optional[Callable] = None) -> List[StepResult]:
        """Executes a batch of unblocked steps in parallel."""
        completed_step_ids = {r.step_id for r in previous_history if r.success}
        failed_step_ids = {r.step_id for r in previous_history if not r.success}
        
        # If any prior step failed, we shouldn't execute anything until replanned
        if failed_step_ids:
            return []
            
        currently_running: Set[str] = set()
        executable = self._get_executable_steps(plan, completed_step_ids, currently_running)
        
        if not executable:
            return []
            
        results = []
        
        # Execute the current layer of independent steps in parallel
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(executable))) as executor:
            future_to_step = {executor.submit(self._execute_single_step, step): step for step in executable}
            
            for future in as_completed(future_to_step):
                step = future_to_step[future]
                try:
                    res = future.result()
                    results.append(res)
                    if on_step_complete:
                        on_step_complete(res)
                except Exception as e:
                    # Thread pool exception
                    err_res = StepResult(step.step_id, False, None, str(e), 0)
                    results.append(err_res)
                    if on_step_complete:
                        on_step_complete(err_res)
                        
        return results
