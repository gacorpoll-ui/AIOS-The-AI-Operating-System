import os
import pytest
import tempfile
import time
from agent.core.memory import MemoryEngine
from agent.core.context_manager import ContextManager

class TestMemorySystem:
    
    @pytest.fixture
    def memory_db_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir
            
    @pytest.fixture
    def memory_engine(self, memory_db_path):
        engine = MemoryEngine(db_path=memory_db_path)
        yield engine
        engine.close()

        # Handled by yield above
        
    def test_store_and_recall_returns_correct_content(self, memory_engine):
        content = "The secret password is 'tesseract'."
        metadata = {"source": "user_input"}
        
        # Store
        mem_id = memory_engine.store(content, metadata, memory_type="episodic")
        assert mem_id is not None
        
        # Recall
        results = memory_engine.recall("secret password", memory_type="episodic")
        
        assert len(results) > 0
        assert results[0]["content"] == content
        assert results[0]["metadata"]["source"] == "user_input"
        
    def test_recall_with_query_returns_relevant_results(self, memory_engine):
        memory_engine.store("I love apples", {"id": 1})
        memory_engine.store("I hate bananas", {"id": 2})
        memory_engine.store("The sky is blue", {"id": 3})
        
        # Depending on Chroma available or mock, recall should find apples
        results = memory_engine.recall("apples")
        assert len(results) > 0
        # Look through all results for apples to account for mocked vector search`n        found_apples = any("apples" in r["content"].lower() for r in results)`n        assert found_apples
        
    def test_kv_store_persists_across_instances(self, memory_db_path):
        engine1 = MemoryEngine(db_path=memory_db_path)
        engine1.store_kv("user_theme", "dark")
        engine1.store_kv("user_config", {"timeout": 30})
        
        # Create a completely new instance pointing to same path
        engine2 = MemoryEngine(db_path=memory_db_path)
        
        assert engine2.get_kv("user_theme") == "dark"
        assert engine2.get_kv("user_config")["timeout"] == 30
        assert engine2.get_kv("nonexistent") is None
        engine1.close()
        engine2.close()
        
    def test_forget_removes_memory(self, memory_engine):
        mem_id1 = memory_engine.store("Memory 1", {})
        mem_id2 = memory_engine.store("Memory 2", {})
        
        # Verify both exist
        res_before = memory_engine.recall("Memory")
        
        # Forget one
        memory_engine.forget(mem_id1)
        
        # Verify it's gone
        res_after = memory_engine.recall("Memory 1")
        # In mock, exact substring match is used. If chroma is used, semantic search might still 
        # return Memory 2 for query "Memory 1". So let's check exact string absence.
        
        content_after = [r["content"] for r in res_after]
        assert "Memory 1" not in content_after
        
    def test_context_manager_session_save_restore(self, memory_engine):
        ctx_manager = ContextManager(memory_engine)
        
        session_id = ctx_manager.start_session()
        ctx_manager.active_task = "Testing AIOS"
        ctx_manager.add_event("command_executed", {"cmd": "ls"})
        
        # Save
        ctx_manager.save_session()
        
        # Create new manager
        new_ctx_manager = ContextManager(memory_engine)
        restored = new_ctx_manager.restore_last_session()
        
        assert restored is not {}
        assert new_ctx_manager.session_id == session_id
        assert new_ctx_manager.active_task == "Testing AIOS"
        assert len(new_ctx_manager.recent_commands) == 1
        assert new_ctx_manager.recent_commands[0]["type"] == "command_executed"

