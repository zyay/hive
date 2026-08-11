"""
Vector-based long-term memory using ChromaDB + sentence-transformers.
Replaces keyword matching with semantic similarity search.
"""

import uuid
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_chroma_client = None
_model = None


def _get_client():
    global _chroma_client
    if _chroma_client is None:
        import chromadb
        _chroma_client = chromadb.PersistentClient(path="hive_memory")
    return _chroma_client


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


class VectorMemory:
    """Semantic memory for an agent using vector embeddings."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.collection_name = f"memory_{agent_id}"

    def _get_collection(self):
        client = _get_client()
        return client.get_or_create_collection(
            self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def remember(self, content: str, metadata: dict = None) -> str:
        """Store a memory with semantic embedding."""
        collection = self._get_collection()
        model = _get_model()
        memory_id = str(uuid.uuid4())[:8]
        embedding = model.encode([content])[0].tolist()

        collection.add(
            ids=[memory_id],
            documents=[content],
            embeddings=[embedding],
            metadatas=[metadata or {"type": "general"}],
        )
        logger.info(f"Memory stored for agent {self.agent_id}: {content[:50]}")
        return memory_id

    def recall(self, query: str, limit: int = 5) -> list[dict]:
        """Recall memories by semantic similarity."""
        collection = self._get_collection()
        if collection.count() == 0:
            return []

        model = _get_model()
        query_embedding = model.encode([query])[0].tolist()

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(limit, collection.count()),
        )

        memories = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            memories.append({
                "content": doc,
                "metadata": meta,
                "similarity": round(1 - dist, 4),
            })
        return memories

    def list_all(self, limit: int = 50) -> list[dict]:
        """List all memories for this agent."""
        collection = self._get_collection()
        if collection.count() == 0:
            return []

        results = collection.get(limit=min(limit, collection.count()))
        return [
            {"id": id_, "content": doc, "metadata": meta}
            for id_, doc, meta in zip(results["ids"], results["documents"], results["metadatas"])
        ]

    def forget(self, memory_id: str) -> bool:
        """Delete a specific memory."""
        collection = self._get_collection()
        try:
            collection.delete(ids=[memory_id])
            return True
        except Exception:
            return False

    def clear(self) -> int:
        """Delete all memories for this agent."""
        client = _get_client()
        count = self._get_collection().count()
        try:
            client.delete_collection(self.collection_name)
        except Exception:
            pass
        return count

    @property
    def count(self) -> int:
        return self._get_collection().count()
