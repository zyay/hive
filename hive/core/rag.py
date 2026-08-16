"""
RAG Pipeline — Document upload, chunking, embedding, and retrieval-augmented generation.
Supports PDF, TXT, MD, and code files. Uses ChromaDB for vector storage.
"""

import os
import uuid
import hashlib
import logging
import mimetypes
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads")
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


@dataclass
class Document:
    """A document in the RAG system."""
    id: str
    filename: str
    content: str
    chunks: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    collection_name: str = ""


def _get_chroma_client():
    """Get or create ChromaDB persistent client."""
    import chromadb
    return chromadb.PersistentClient(path="hive_rag")


def _get_embedding_model():
    """Get or create sentence transformer model."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


def extract_text(file_path: str) -> str:
    """Extract text content from various file formats."""
    path = Path(file_path)
    ext = path.suffix.lower()
    
    if ext in (".txt", ".md", ".py", ".js", ".ts", ".java", ".go", ".rs", ".c", ".cpp", ".h", ".yaml", ".yml", ".json", ".toml", ".xml", ".html", ".css", ".sh", ".bat", ".sql", ".r", ".rb", ".php", ".swift", ".kt"):
        return path.read_text(encoding="utf-8", errors="replace")
    
    if ext == ".pdf":
        try:
            import PyPDF2
            text = ""
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            return text
        except ImportError:
            logger.warning("PyPDF2 not installed — PDF extraction unavailable")
            return ""
    
    if ext == ".csv":
        return path.read_text(encoding="utf-8", errors="replace")
    
    logger.warning(f"Unsupported file type: {ext}")
    return ""


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks for embedding."""
    if not text.strip():
        return []
    
    words = text.split()
    chunks = []
    start = 0
    
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk)
        start += chunk_size - overlap
    
    return chunks


def file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()[:16]


class RAGPipeline:
    """Retrieval-Augmented Generation pipeline for a collection of documents."""

    def __init__(self, collection_name: str = "hive_documents"):
        self.collection_name = collection_name
        self._client = None
        self._model = None

    @property
    def client(self):
        if self._client is None:
            self._client = _get_chroma_client()
        return self._client

    @property
    def model(self):
        if self._model is None:
            self._model = _get_embedding_model()
        return self._model

    @property
    def collection(self):
        return self.client.get_or_create_collection(
            self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def ingest_file(self, file_path: str, metadata: dict = None) -> Document:
        """Ingest a file into the RAG system — extract, chunk, embed, store."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        content = extract_text(file_path)
        if not content.strip():
            raise ValueError(f"No text content extracted from {path.name}")

        chunks = chunk_text(content)
        if not chunks:
            raise ValueError(f"No chunks generated from {path.name}")

        doc_id = file_hash(file_path)
        doc = Document(
            id=doc_id,
            filename=path.name,
            content=content,
            chunks=chunks,
            metadata=metadata or {},
            collection_name=self.collection_name,
        )

        embeddings = self.model.encode(chunks).tolist()
        ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {**doc.metadata, "doc_id": doc_id, "filename": path.name, "chunk_index": i, "total_chunks": len(chunks)}
            for i in range(len(chunks))
        ]

        self.collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        logger.info(f"Ingested {path.name}: {len(chunks)} chunks, {len(content)} chars")
        return doc

    def ingest_text(self, text: str, filename: str = "inline", metadata: dict = None) -> Document:
        """Ingest raw text directly."""
        chunks = chunk_text(text)
        if not chunks:
            raise ValueError("No chunks generated from text")

        doc_id = hashlib.sha256(text.encode()).hexdigest()[:16]
        doc = Document(
            id=doc_id,
            filename=filename,
            content=text,
            chunks=chunks,
            metadata=metadata or {},
            collection_name=self.collection_name,
        )

        embeddings = self.model.encode(chunks).tolist()
        ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {**doc.metadata, "doc_id": doc_id, "filename": filename, "chunk_index": i, "total_chunks": len(chunks)}
            for i in range(len(chunks))
        ]

        self.collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        logger.info(f"Ingested text '{filename}': {len(chunks)} chunks")
        return doc

    def query(self, question: str, top_k: int = 5) -> list[dict]:
        """Query the RAG system for relevant document chunks."""
        if self.collection.count() == 0:
            return []

        query_embedding = self.model.encode([question])[0].tolist()
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.collection.count()),
        )

        retrieved = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            retrieved.append({
                "content": doc,
                "filename": meta.get("filename", "unknown"),
                "doc_id": meta.get("doc_id", ""),
                "chunk_index": meta.get("chunk_index", 0),
                "relevance_score": 1 - dist,
            })

        return retrieved

    def build_context(self, question: str, top_k: int = 5, max_chars: int = 3000) -> str:
        """Build a context string from retrieved chunks for LLM augmentation."""
        results = self.query(question, top_k)
        if not results:
            return ""

        context_parts = []
        total = 0
        for r in results:
            chunk = f"[Source: {r['filename']}]\n{r['content']}"
            if total + len(chunk) > max_chars:
                remaining = max_chars - total
                if remaining > 100:
                    context_parts.append(chunk[:remaining] + "...")
                break
            context_parts.append(chunk)
            total += len(chunk)

        return "\n\n---\n\n".join(context_parts)

    def delete_document(self, doc_id: str):
        """Delete all chunks for a document."""
        results = self.collection.get(where={"doc_id": doc_id})
        if results and results["ids"]:
            self.collection.delete(ids=results["ids"])
            logger.info(f"Deleted document {doc_id}: {len(results['ids'])} chunks removed")

    def list_documents(self) -> list[dict]:
        """List all ingested documents."""
        all_data = self.collection.get()
        if not all_data or not all_data["ids"]:
            return []

        docs = {}
        for meta in all_data["metadatas"]:
            doc_id = meta.get("doc_id", "")
            if doc_id not in docs:
                docs[doc_id] = {
                    "doc_id": doc_id,
                    "filename": meta.get("filename", "unknown"),
                    "chunks": meta.get("total_chunks", 0),
                    **{k: v for k, v in meta.items() if k not in ("doc_id", "filename", "chunk_index", "total_chunks")},
                }

        return list(docs.values())

    def clear(self):
        """Clear all documents from the collection."""
        self.client.delete_collection(self.collection_name)
        logger.info(f"Cleared RAG collection: {self.collection_name}")

    @property
    def count(self) -> int:
        """Total number of chunks in the collection."""
        return self.collection.count()


# Global RAG instance
rag_pipeline = RAGPipeline()
