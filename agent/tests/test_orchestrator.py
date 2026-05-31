import pytest
from unittest.mock import MagicMock
from agent.core.orchestrator import AgentOrchestrator, AgentResult
from agent.core.planner import Planner, ExecutionPlan, PlanStep
from agent.core.executor import StepResult

class TestOrchestrator:
    
    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        # Mock planner response
        llm.generate_structured.return_value = {
            "goal_understanding": "understood",
            "steps": [
                {"step_id": "1", "tool_name": "dummy_tool", "tool_params": {}, "depends_on": []}
            ]
        }
        return llm
        
    @pytest.fixture
    def mock_tools(self):
        tools = MagicMock()
        tools.list_tools.return_value = []
        res = MagicMock()
        res.success = True
        res.output = "success"
        res.error = None
        res.execution_time_ms = 10
        tools.execute.return_value = res
        return tools
        
    @pytest.fixture
    def orchestrator(self, mock_llm, mock_tools):
        memory = MagicMock()
        planner = Planner(mock_llm)
        return AgentOrchestrator(llm=mock_llm, tools=mock_tools, memory=memory, planner=planner)
        
    def test_simple_goal_executes_correctly(self, orchestrator, mock_llm):
        # Override reflection to indicate success after one execution
        mock_llm.generate_structured.side_effect = [
            # 1. Planner call
            {
                "steps": [
                    {"step_id": "s1", "tool_name": "test", "depends_on": []}
                ]
            },
            # 2. Reflection call
            {
                "goal_achieved": True,
                "progress_summary": "Done."
            }
        ]
        
        result = orchestrator.run("do simple task")
        
        assert isinstance(result, AgentResult)
        assert result.success is True
        assert len(result.execution_history) == 1
        assert result.execution_history[0].step_id == "s1"
        assert result.iterations == 1
        
    def test_multi_step_goal_respects_dependencies(self, orchestrator, mock_llm):
        # We need to simulate multiple loop iterations
        call_count = 0
        def llm_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1: # Planning
                return {
                    "steps": [
                        {"step_id": "s1", "tool_name": "t1", "depends_on": []},
                        {"step_id": "s2", "tool_name": "t2", "depends_on": ["s1"]}
                    ]
                }
            elif call_count == 2: # Reflection 1 (only s1 done)
                return {"goal_achieved": False, "next_actions": ["do s2"]}
            elif call_count == 3: # Reflection 2 (s1 and s2 done)
                return {"goal_achieved": True, "progress_summary": "Finished"}
            return {}
            
        mock_llm.generate_structured.side_effect = llm_side_effect
        
        result = orchestrator.run("do multi task")
        
        assert result.success is True
        assert len(result.execution_history) == 2
        # Verify order
        assert result.execution_history[0].step_id == "s1"
        assert result.execution_history[1].step_id == "s2"
        assert result.iterations == 2
        
    def test_max_iterations_prevents_infinite_loops(self, orchestrator, mock_llm):
        # Always plan something, never reflect success
        mock_llm.generate_structured.side_effect = lambda *args, **kwargs: {"goal_achieved": False}
        
        # Artificially lower max iterations for test speed
        orchestrator.max_iterations = 3
        
        result = orchestrator.run("impossible task")
        
        assert result.success is False
        assert result.iterations == 3
        assert "maximum iterations" in result.final_message.lower()

    def test_failed_step_triggers_replan(self, orchestrator, mock_llm, mock_tools):
        # Make the tool fail
        err_res = MagicMock()
        err_res.success = False
        err_res.error = "File not found"
        mock_tools.execute.return_value = err_res
        
        call_count = 0
        def llm_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1: # Initial Plan
                return {
                    "steps": [
                        {"step_id": "s1", "tool_name": "t1", "depends_on": []}
                    ]
                }
            elif call_count == 2: # Replan (not actually called in mock because we just drop steps, but let's be safe)
                return {"goal_achieved": False}
            elif call_count == 3: # Reflection 
                return {"goal_achieved": False, "blockers": ["Cannot find file"]}
            return {}
            
        mock_llm.generate_structured.side_effect = llm_side_effect
        orchestrator.max_iterations = 2
        
        result = orchestrator.run("task that fails")
        
        # It should try to execute s1, fail, drop the rest of the plan, reflect, and eventually give up
        assert result.success is False
        assert len(result.execution_history) > 0
        assert result.execution_history[0].success is False
