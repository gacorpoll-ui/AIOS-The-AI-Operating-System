"""Module description for memory"""
import os
import json
import uuid
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Union

# Optional dependencies for robust fallback
try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logging.warning("chromadb not available. Using mock implementation.")

try:
    from cryptography.fernet import Fernet
    FERNET_AVAILABLE = True
except ImportError:
    FERNET_AVAILABLE = False
    logging.warning("cryptography not available. Using base64 encoding instead of true encryption.")
    import base64

logger = logging.getLogger(__name__)

class MemoryEngine:
    """Persistent semantic memory engine combining SQLite (KV) and ChromaDB (Vector)."""
    
    def __init__(self, db_path: str, collection_name: str = "aios_memory", encryption_key: Optional[bytes] = None):
        self.db_path = db_path
        os.makedirs(db_path, exist_ok=True)
        
        # Initialize SQLite for KV store with WAL mode
        self.sqlite_path = os.path.join(db_path, "kv_store.db")
        self._init_sqlite()
        
        # Setup Encryption
        if FERNET_AVAILABLE:
            if not encryption_key:
                # In production, this should be provided securely. 
                # For initialization, we generate one and store it securely or expect it.
                encryption_key = Fernet.generate_key()
            self.cipher_suite = Fernet(encryption_key)
        else:
            self.cipher_suite = None
            
        # Initialize ChromaDB for semantic search
        self.collection_name = collection_name
        self._init_chroma()
        
        # Mock storage for when Chroma is not available
        self._mock_vector_store = []
        
    def _init_sqlite(self):
        """Initialize SQLite database with WAL mode."""
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute('''
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
    def _init_chroma(self):
        """Initialize ChromaDB persistent client."""
        if CHROMA_AVAILABLE:
            self.chroma_client = chromadb.PersistentClient(path=os.path.join(self.db_path, "chroma"))
            self.collection = self.chroma_client.get_or_create_collection(name=self.collection_name)
        else:
            self.chroma_client = None
            self.collection = None
            
    def _encrypt(self, text: str) -> str:
        """Encrypt content using Fernet."""
        if FERNET_AVAILABLE and self.cipher_suite:
            return self.cipher_suite.encrypt(text.encode('utf-8')).decode('utf-8')
        else:
            # Fallback mock encryption
            return base64.b64encode(text.encode('utf-8')).decode('utf-8')
            
    def _decrypt(self, text: str) -> str:
        """Decrypt content using Fernet."""
        if FERNET_AVAILABLE and self.cipher_suite:
            try:
                return self.cipher_suite.decrypt(text.encode('utf-8')).decode('utf-8')
            except Exception as e:
                logger.error(f"Decryption failed: {e}")
                return "[ENCRYPTED_CONTENT_UNREADABLE]"
        else:
            # Fallback mock decryption
            try:
                return base64.b64decode(text.encode('utf-8')).decode('utf-8')
            except Exception as e:
                return text

    def store(self, content: str, metadata: dict, memory_type: str = "episodic") -> str:
        """Embeds content, encrypts, and stores in ChromaDB. Returns memory_id."""
        # Chunking: max memory entry size 10,000 chars
        MAX_CHARS = 10000
        if len(content) > MAX_CHARS:
            content = content[:MAX_CHARS]
            logger.warning(f"Content chunked to {MAX_CHARS} characters.")
            
        memory_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        enriched_metadata = metadata.copy()
        enriched_metadata.update({
            "memory_type": memory_type,
            "timestamp": timestamp
        })
        
        encrypted_content = self._encrypt(content)
        
        if CHROMA_AVAILABLE and self.collection:
            # In a full integration, you would generate embeddings with LocalLLM first.
            # Chroma default embedding model will be used if no embeddings are explicitly provided.
            self.collection.add(
                documents=[encrypted_content],
                metadatas=[enriched_metadata],
                ids=[memory_id]
            )
        else:
            self._mock_vector_store.append({
                "id": memory_id,
                "document": encrypted_content,
                "metadata": enriched_metadata,
                "original_content": content # Keep for mock retrieval testing
            })
            
        return memory_id

    def recall(self, query: str, n_results: int = 5, memory_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Semantic search, returns list of memories."""
        results_out = []
        
        if CHROMA_AVAILABLE and self.collection:
            where_clause = {"memory_type": memory_type} if memory_type else None
            
            # Simple query - ChromaDB handles embedding internally with its default function
            # If using custom embeddings, we would pass 'query_embeddings' instead
            try:
                # Handle cases where collection is empty
                if self.collection.count() == 0:
                    return []
                    
                n_res = min(n_results, self.collection.count())
                if n_res == 0: return []
                
                results = self.collection.query(
                    query_texts=[query],
                    n_results=n_res,
                    where=where_clause
                )
                
                if results['documents'] and len(results['documents']) > 0:
                    for i, doc in enumerate(results['documents'][0]):
                        decrypted_doc = self._decrypt(doc)
                        meta = results['metadatas'][0][i] if results['metadatas'] else {}
                        # Relevance score is inverted distance
                        distance = results['distances'][0][i] if results.get('distances') else 0
                        
                        results_out.append({
                            "content": decrypted_doc,
                            "metadata": meta,
                            "relevance_score": 1.0 / (1.0 + distance),
                            "timestamp": meta.get("timestamp", datetime.now(timezone.utc).isoformat())
                        })
            except Exception as e:
                logger.error(f"Recall failed: {e}")
        else:
            # Mock semantic search
            for item in reversed(self._mock_vector_store):
                if memory_type and item["metadata"]["memory_type"] != memory_type:
                    continue
                    
                if query.lower() in item["original_content"].lower():
                    results_out.append({
                        "content": self._decrypt(item["document"]),
                        "metadata": item["metadata"],
                        "relevance_score": 0.9,
                        "timestamp": item["metadata"]["timestamp"]
                    })
                    if len(results_out) >= n_results:
                        break
                        
        return results_out

    def store_kv(self, key: str, value: Any) -> None:
        """Stores key-value in SQLite."""
        value_str = json.dumps(value)
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO kv_store (key, value)
                VALUES (?, ?)
            ''', (key, value_str))

    def get_kv(self, key: str, default: Any = None) -> Any:
        """Retrieves from SQLite."""
        with sqlite3.connect(self.sqlite_path) as conn:
            cursor = conn.execute('SELECT value FROM kv_store WHERE key = ?', (key,))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return default

    def get_context_summary(self, last_n_hours: int = 24) -> str:
        """Returns AI-generated summary of recent activity."""
        # For full implementation, this queries the LLM with recent memories
        # Currently acts as a stub
        return f"Summary of activity over the last {last_n_hours} hours."

    def forget(self, memory_id: str) -> None:
        """Removes specific memory."""
        if CHROMA_AVAILABLE and self.collection:
            self.collection.delete(ids=[memory_id])
        else:
            self._mock_vector_store = [m for m in self._mock_vector_store if m["id"] != memory_id]

    def close(self) -> None:
        """Clean up resources (close ChromaDB/SQLite connections)."""
        # Force chromadb to close its SQLite connections if available
        if CHROMA_AVAILABLE and hasattr(self, 'chroma_client') and self.chroma_client:
            try:
                self.chroma_client.clear_system_cache()
            except Exception as e:
                pass
            self.collection = None
            self.chroma_client = None
        import gc
        gc.collect()
        import time
        time.sleep(0.1)

    def forget_all(self, memory_type: Optional[str] = None) -> int:
        """Wipe memories by type, returns count deleted."""
        count = 0
        if CHROMA_AVAILABLE and self.collection:
            if memory_type:
                where_clause = {"memory_type": memory_type}
                # Chroma doesn't return deleted count easily without fetching first, 
                # but we'll do our best.
                to_delete = self.collection.get(where=where_clause)
                if to_delete and to_delete['ids']:
                    count = len(to_delete['ids'])
                    self.collection.delete(ids=to_delete['ids'])
            else:
                to_delete = self.collection.get()
                if to_delete and to_delete['ids']:
                    count = len(to_delete['ids'])
                    # Wipe everything
                    self.chroma_client.delete_collection(self.collection_name)
                    self.collection = self.chroma_client.create_collection(self.collection_name)
        else:
            if memory_type:
                initial_len = len(self._mock_vector_store)
                self._mock_vector_store = [m for m in self._mock_vector_store if m["metadata"].get("memory_type") != memory_type]
                count = initial_len - len(self._mock_vector_store)
            else:
                count = len(self._mock_vector_store)
                self._mock_vector_store = []
                
        return count
