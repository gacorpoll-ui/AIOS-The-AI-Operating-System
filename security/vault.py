import os
import sqlite3
import base64
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    FERNET_AVAILABLE = True
except ImportError:
    FERNET_AVAILABLE = False
    logging.warning("cryptography not available. SecureVault will use weak mock encryption.")

class SecureVault:
    """Encrypted storage for sensitive data like API keys."""
    
    def __init__(self, db_path: str = "~/.aios/vault.db", passphrase: str = "default_passphrase"):
        self.db_path = os.path.expanduser(db_path)
        dir_path = os.path.dirname(self.db_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        self._init_db()
        self._setup_encryption(passphrase)
        
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS secrets (
                    key TEXT PRIMARY KEY,
                    encrypted_value TEXT
                )
            ''')
            
    def _setup_encryption(self, passphrase: str):
        if FERNET_AVAILABLE:
            # Fixed salt for this implementation, in reality should be stored securely
            salt = b"aios_vault_salt_123"
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))
            self.fernet = Fernet(key)
        else:
            self.fernet = None
            
    def _encrypt(self, value: str) -> str:
        if self.fernet:
            return self.fernet.encrypt(value.encode()).decode()
        # Mock encryption if cryptography is missing
        return "ENC_" + base64.b64encode(value.encode()).decode()
        
    def _decrypt(self, encrypted_value: str) -> str:
        if self.fernet:
            return self.fernet.decrypt(encrypted_value.encode()).decode()
        # Mock decryption
        if encrypted_value.startswith("ENC_"):
            return base64.b64decode(encrypted_value[4:].encode()).decode()
        return encrypted_value

    def store_secret(self, key: str, value: str) -> None:
        encrypted = self._encrypt(value)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('INSERT OR REPLACE INTO secrets (key, encrypted_value) VALUES (?, ?)', (key, encrypted))
            
    def get_secret(self, key: str) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT encrypted_value FROM secrets WHERE key = ?', (key,))
            row = cursor.fetchone()
            if row:
                try:
                    return self._decrypt(row[0])
                except Exception as e:
                    logger.error(f"Failed to decrypt secret {key}: {e}")
                    return None
            return None
            
    def delete_secret(self, key: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('DELETE FROM secrets WHERE key = ?', (key,))
            return cursor.rowcount > 0
            
    def list_keys(self) -> List[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT key FROM secrets')
            return [row[0] for row in cursor.fetchall()]
