import logging
import time
import hashlib
from typing import List, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ActionRecord:
    action_type: str
    action_target: str
    before_dom_hash: str = ""
    after_dom_hash: str = ""
    screenshot_before: str = ""
    screenshot_after: str = ""
    success: bool = False
    task_type: str = "unknown"
    timestamp: float = field(default_factory=time.time)
    execution_duration: float = 0.0


class PineconeStore:
    def __init__(self, api_key: str = None, index_name: str = "jarvis-actions"):
        self.api_key = api_key
        self.index_name = index_name
        self.index = None
        self.fallback_store: List[Dict] = []
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return self.index is not None

        if not self.api_key:
            logger.warning("No Pinecone API key provided, using in-memory fallback")
            self._initialized = True
            return False

        try:
            from pinecone import Pinecone
            pc = Pinecone(api_key=self.api_key)
            self.index = pc.Index(self.index_name)
            logger.info("Pinecone connected successfully")
            self._initialized = True
            return True
        except ImportError:
            logger.warning("Pinecone not installed, using in-memory fallback")
            self._initialized = True
            return False
        except Exception as e:
            logger.warning(f"Failed to connect to Pinecone: {e}, using in-memory fallback")
            self._initialized = True
            return False

    def store_action(self, record: ActionRecord):
        vector = {
            "id": f"{record.action_type}_{record.action_target}_{int(record.timestamp * 1000)}",
            "values": self._embed_action(record),
            "metadata": {
                "action_type": record.action_type,
                "action_target": record.action_target,
                "success": record.success,
                "task_type": record.task_type,
                "timestamp": record.timestamp,
                "execution_duration": record.execution_duration,
            }
        }

        if self._ensure_initialized() and self.index:
            try:
                self.index.upsert([vector])
                logger.info(f"Stored action in Pinecone: {record.action_type}")
            except Exception as e:
                logger.warning(f"Failed to store in Pinecone: {e}")
                self.fallback_store.append(vector)
        else:
            self.fallback_store.append(vector)

        logger.info(f"Stored action: {record.action_type} -> {record.action_target}")

    def query_similar(self, action_type: str, target: str = "", top_k: int = 5) -> List[Dict]:
        query_vector = self._generate_query_vector(action_type, target)

        if self._ensure_initialized() and self.index:
            try:
                results = self.index.query(
                    vector=query_vector,
                    top_k=top_k,
                    filter={"action_type": action_type} if action_type else None,
                    include_metadata=True
                )
                return results.get("matches", [])
            except Exception as e:
                logger.warning(f"Failed to query Pinecone: {e}")

        filtered = [s for s in self.fallback_store if s["metadata"].get("action_type") == action_type]
        return filtered[:top_k] if filtered else self.fallback_store[:top_k]

    def _embed_action(self, record: ActionRecord) -> List[float]:
        action_str = f"{record.action_type}_{record.action_target}"
        hash_bytes = hashlib.sha256(action_str.encode()).digest()
        values = [b / 255.0 for b in hash_bytes[:128]]
        values.extend([0.0] * (768 - len(values)))
        return values

    def _generate_query_vector(self, action_type: str, target: str) -> List[float]:
        action_str = f"{action_type}_{target}"
        hash_bytes = hashlib.sha256(action_str.encode()).digest()
        values = [b / 255.0 for b in hash_bytes[:128]]
        values.extend([0.0] * (768 - len(values)))
        return values

    def get_stats(self) -> Dict:
        return {
            "total_stored": len(self.fallback_store),
            "pinecone_connected": self.index is not None,
        }
