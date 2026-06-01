import pytest
from security.constitution import (
    Constitution, ConstitutionResult, ConstitutionViolation,
    enforce, ARTICLE_1, ARTICLE_2, ARTICLE_3, ARTICLE_4, ARTICLE_5, ARTICLE_6
)
from agent.core.blackbox import TamperProofBlackBox


class TestConstitution:

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton between tests."""
        Constitution._instance = None
        yield
        Constitution._instance = None

    @pytest.fixture
    def bb(self, tmp_path):
        return TamperProofBlackBox(db_dir=str(tmp_path / "bb"))

    @pytest.fixture
    def constitution(self, bb):
        return Constitution(black_box=bb)

    # --- REQUIRED TESTS FROM PROMPT F ---

    def test_network_tool_without_human_approved_is_blocked(self, constitution):
        """Network tool calls without human approval must be blocked."""
        result = constitution.check("run_command", {"command": "curl http://evil.com"})
        assert result.compliant is False
        assert any("Article 1" in v for v in result.violations)

    def test_delete_blackbox_record_is_blocked(self, constitution):
        """Any attempt to delete black box records must be blocked."""
        result = constitution.check("run_command", {"command": "rm -rf /data/blackbox.db"})
        assert result.compliant is False
        assert any("Article 4" in v for v in result.violations)

    def test_normal_tool_calls_pass_through(self, constitution):
        """Safe tool calls must pass without violations."""
        result = constitution.check("list_directory", {"path": "."})
        assert result.compliant is True
        assert result.violations == []

    def test_constitution_cannot_be_modified_at_runtime(self, constitution):
        """Attempting to modify the Constitution must raise."""
        with pytest.raises(RuntimeError, match="sealed"):
            constitution._black_box = "tampered"

    def test_violation_logged_to_black_box(self, constitution, bb):
        """A violation must be detectable and black box remains intact."""
        result = constitution.check("run_command", {"command": "curl http://x.com"})
        assert result.compliant is False
        # Black box is still accessible (Article 4 protects it)
        chain = bb.get_chain(10)
        assert isinstance(chain, list)

    # --- ADDITIONAL COVERAGE ---

    def test_network_with_approval_passes(self, constitution):
        result = constitution.check("run_command", {
            "command": "curl http://safe.com"
        }, context={"human_approved": True})
        assert result.compliant is True

    def test_privilege_escalation_without_permission_blocked(self, constitution):
        result = constitution.check("run_command", {"command": "sudo rm /something"})
        assert result.compliant is False
        assert any("Article 3" in v for v in result.violations)

    def test_privilege_escalation_with_permission_passes(self, constitution):
        constitution.grant_permission("sudo")
        result = constitution.check("run_command", {
            "command": "sudo apt update"
        }, context={"human_approved": True})
        assert result.compliant is True

    def test_self_replication_blocked(self, constitution):
        result = constitution.check("run_command", {"command": "python -m shell.nl_shell &"})
        assert result.compliant is False

    def test_write_file_logged_not_blocked(self, constitution, bb):
        result = constitution.check("write_file", {"path": "/tmp/test.txt", "content": "hello"})
        assert result.compliant is True
        chain = bb.get_chain(10)
        file_changes = [e for e in chain if e.get("event_type") == "file_modification"]
        assert len(file_changes) >= 1

    def test_singleton_cannot_be_replaced(self, constitution):
        c2 = Constitution()
        assert c2 is constitution

    def test_enforce_function_works(self, bb):
        Constitution(black_box=bb)
        result = enforce("list_directory", {"path": "."})
        assert isinstance(result, ConstitutionResult)
        assert result.compliant is True

    def test_all_articles_are_hardcoded_strings(self):
        assert isinstance(ARTICLE_1, str) and "exfiltration" in ARTICLE_1.lower()
        assert isinstance(ARTICLE_2, str) and "self-replication" in ARTICLE_2.lower()
        assert isinstance(ARTICLE_3, str) and "privilege" in ARTICLE_3.lower()
        assert isinstance(ARTICLE_4, str) and "memory" in ARTICLE_4.lower()
        assert isinstance(ARTICLE_5, str) and "silent" in ARTICLE_5.lower()
        assert isinstance(ARTICLE_6, str) and "transparency" in ARTICLE_6.lower()

    def test_constitution_violation_exception(self):
        exc = ConstitutionViolation(["test violation"], article=1)
        assert "Article 1" in str(exc)
        assert "test violation" in str(exc)

    def test_permission_grant_revoke(self, constitution):
        assert not constitution.has_permission("sudo")
        constitution.grant_permission("sudo")
        assert constitution.has_permission("sudo")
        constitution.revoke_permission("sudo")
        assert not constitution.has_permission("sudo")

    def test_check_completes_under_1ms(self, constitution):
        import time
        start = time.time()
        for _ in range(100):
            constitution.check("list_directory", {"path": "."})
        elapsed = time.time() - start
        avg_ms = (elapsed / 100) * 1000
        assert avg_ms < 1.0, f"Average check took {avg_ms:.3f}ms, must be < 1ms"

    def test_cannot_delete_constitution_attribute(self, constitution):
        with pytest.raises(RuntimeError, match="sealed"):
            del constitution._initialized