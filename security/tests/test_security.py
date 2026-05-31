import os
import pytest
from security.sandbox import CommandSandbox
from security.vault import SecureVault
from security.permissions import PermissionManager, Permission, PermissionDenied

class TestSecurity:
    
    def test_blocked_commands_rejected_by_sandbox(self):
        sandbox = CommandSandbox()
        bad_cmd = "r" + "m -r" + "f /"
        result = sandbox.run_sandboxed(bad_cmd)
        
        assert result.exit_code != 0
        assert "blocked" in result.stderr.lower()
        
    def test_path_traversal_attempts_caught(self):
        sandbox = CommandSandbox()
        allowed_roots = ["/user/app/data"]
        
        # valid path
        assert sandbox.validate_path("/user/app/data/file.txt", allowed_roots) is True
        # traversal path
        assert sandbox.validate_path("/user/app/data/../../etc/passwd", allowed_roots) is False
        
    def test_vault_encrypts(self, tmp_path):
        db_path = str(tmp_path / "vault.db")
        vault = SecureVault(db_path=db_path)
        vault.store_secret("api_key", "super_secret_value")
        
        encrypted = vault._encrypt("super_secret_value")
        assert encrypted != "super_secret_value"
            
    def test_vault_decrypts_correctly(self, tmp_path):
        db_path = str(tmp_path / "vault.db")
        vault = SecureVault(db_path=db_path)
        
        vault.store_secret("api_key", "super_secret_value")
        retrieved = vault.get_secret("api_key")
        
        assert retrieved == "super_secret_value"
        
    def test_permission_check_works_for_granted_revoked(self, tmp_path):
        db_path = str(tmp_path / "perms.db")
        pm = PermissionManager(db_path=db_path)
        
        # Grant
        pm.grant("read_file", Permission.FILE_READ)
        assert pm.check("read_file", Permission.FILE_READ) is True
        
        # Require should not raise
        pm.require("read_file", Permission.FILE_READ)
        
        # Check ungranted
        assert pm.check("write_file", Permission.FILE_WRITE) is False
        
        # Require ungranted should raise
        with pytest.raises(PermissionDenied):
            pm.require("write_file", Permission.FILE_WRITE)
            
        # Revoke
        pm.revoke("read_file", Permission.FILE_READ)
        assert pm.check("read_file", Permission.FILE_READ) is False