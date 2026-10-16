"""Persistent ChromaDB vector database manager with semantic retrieval."""

import json
import logging
from typing import Any, Dict, List, Optional
import numpy as np

import chromadb
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
from chromadb.utils import embedding_functions

from src.config import Settings, settings as global_settings
from src.chunker import chunk_article
from src.models import (
    ArticleRecord,
    ArticleStatus,
    DocumentChunk,
    ImageCitation,
    SourceCitation,
)

logger = logging.getLogger("knowledge_brain.vector_store")


class MockEmbeddingFunction(EmbeddingFunction):
    """Deterministic, fast mock embedding function for offline unit tests.

    Produces normalized 384-dimensional vectors based on word frequencies.
    Zero external dependencies, zero network access, runs in microseconds.
    """

    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    @staticmethod
    def name() -> str:
        return "mock"

    def get_config(self) -> dict:
        return {"dimension": self.dimension}

    @classmethod
    def build_from_config(cls, config: dict):
        return cls(dimension=config.get("dimension", 384))

    def __call__(self, input: Documents) -> Embeddings:
        embeddings: List[List[float]] = []
        for doc in input:
            vec = np.zeros(self.dimension, dtype=np.float32)
            words = doc.lower().split()
            for w in words:
                # Deterministic hash to dimension index
                idx = abs(hash(w)) % self.dimension
                vec[idx] += 1.0

            # L2 normalize
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            embeddings.append(vec.tolist())
        return embeddings


def get_embedding_function(
    provider: str,
    model_name: str = "all-MiniLM-L6-v2",
) -> EmbeddingFunction:
    """Factory creating the appropriate embedding function based on configuration."""
    provider_clean = (provider or "default").lower().strip()

    if provider_clean == "mock":
        return MockEmbeddingFunction()
    elif provider_clean == "sentence_transformers":
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=model_name
        )
    else:
        # Default: Chroma's local ONNX runtime all-MiniLM-L6-v2 (Zero API keys required)
        return embedding_functions.DefaultEmbeddingFunction()


class VectorStore:
    """Manages persistent document indexing, re-indexing, and similarity retrieval."""

    def __init__(
        self,
        config: Optional[Settings] = None,
        client: Optional[chromadb.Client] = None,
        embedding_fn: Optional[EmbeddingFunction] = None,
    ):
        self.config = config or global_settings
        self.config.ensure_directories()

        self.embedding_fn = embedding_fn or get_embedding_function(
            provider=self.config.embedding_provider,
            model_name=self.config.embedding_model,
        )

        if client is not None:
            self.client = client
        else:
            self.client = chromadb.PersistentClient(
                path=str(self.config.chroma_persist_dir)
            )

        self.collection = self.client.get_or_create_collection(
            name=self.config.chroma_collection_name,
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        """Return total number of chunks currently in the vector index."""
        return self.collection.count()

    def delete_article_chunks(self, url: str) -> int:
        """Safely remove all chunks belonging to a specific article URL.

        Used when an article is updated or soft-removed.
        """
        try:
            # Query existing chunks for this url
            existing = self.collection.get(where={"url": url})
            if existing and existing["ids"]:
                chunk_ids = existing["ids"]
                self.collection.delete(ids=chunk_ids)
                logger.info(f"Deleted {len(chunk_ids)} stale chunks for URL: {url}")
                return len(chunk_ids)
        except Exception as e:
            logger.error(f"Error deleting chunks for {url}: {e}")
        return 0

    def index_article(self, article: ArticleRecord) -> int:
        """Chunk and index an article into the vector database.

        Safely purges any older chunks for the same URL first to prevent duplicates.
        """
        # 1. Clean previous chunks for this article URL
        self.delete_article_chunks(article.url)

        # 2. Chunk the article
        chunks: List[DocumentChunk] = chunk_article(
            article=article,
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )
        if not chunks:
            logger.warning(f"No chunks generated for article (empty content): {article.url}")
            return 0

        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for chunk in chunks:
            ids.append(chunk.chunk_id)
            documents.append(chunk.content)
            metadatas.append(
                {
                    "article_id": chunk.article_id,
                    "url": chunk.url,
                    "title": chunk.title,
                    "category": chunk.category or "",
                    "folder": chunk.folder or "",
                    "section": chunk.section or "",
                    "chunk_index": chunk.chunk_index,
                    "total_chunks": chunk.total_chunks,
                    "images_json": json.dumps([img.model_dump() for img in chunk.images]),
                }
            )

        try:
            self.collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )
            logger.info(f"Indexed {len(chunks)} chunks for article: {article.title}")
            return len(chunks)
        except Exception as e:
            logger.error(f"Failed to upsert chunks for {article.url}: {e}")
            raise

    def sync_all_from_state(
        self,
        state: Dict[str, ArticleRecord],
        force: bool = False,
    ) -> Dict[str, int]:
        """Synchronize vector collection from crawler state file.

        - Indexes active articles.
        - Prunes chunks for soft-removed articles.
        """
        indexed_articles = 0
        total_chunks = 0
        removed_articles = 0

        for url, record in state.items():
            if record.status == ArticleStatus.ACTIVE:
                chunks_count = self.index_article(record)
                indexed_articles += 1
                total_chunks += chunks_count
            elif record.status == ArticleStatus.REMOVED:
                deleted = self.delete_article_chunks(url)
                if deleted > 0:
                    removed_articles += 1

        return {
            "indexed_articles": indexed_articles,
            "total_chunks": total_chunks,
            "removed_articles": removed_articles,
            "collection_total": self.count(),
        }

    def search(
        self,
        query: str,
        top_k: int = 3,
        min_score: Optional[float] = None,
    ) -> List[SourceCitation]:
        """Retrieve most relevant article chunks with similarity scores and attached screenshots.

        Args:
            query: The user query string.
            top_k: Max candidate chunks to return.
            min_score: Minimum similarity score threshold (0.0 to 1.0).

        Returns:
            List of SourceCitation models with attached screenshots.
        """
        threshold = min_score if min_score is not None else self.config.similarity_threshold
        total_in_db = self.count()

        if total_in_db == 0 or not query.strip():
            return []

        fetch_k = min(top_k, total_in_db)

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=fetch_k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.error(f"Vector search failed for query '{query}': {e}")
            return []

        citations: List[SourceCitation] = []

        if not results or not results.get("ids") or not results["ids"][0]:
            return []

        doc_list = results["documents"][0]
        meta_list = results["metadatas"][0]
        dist_list = results["distances"][0]

        for doc_text, meta, distance in zip(doc_list, meta_list, dist_list):
            # In Chroma with cosine space: distance in [0, 2]
            # similarity = 1.0 - distance
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))

            if similarity < threshold:
                continue

            # Parse attached screenshots
            images: List[ImageCitation] = []
            images_json = meta.get("images_json")
            if images_json:
                try:
                    raw_images = json.loads(images_json)
                    images = [ImageCitation.model_validate(img) for img in raw_images]
                except Exception as e:
                    logger.warning(f"Failed to deserialize image metadata: {e}")

            citations.append(
                SourceCitation(
                    title=meta.get("title", "Brilliant Directories Guide"),
                    url=meta.get("url", ""),
                    section=meta.get("section") or None,
                    snippet=doc_text.strip(),
                    score=round(similarity, 4),
                    images=images,
                )
            )

        # Sort descending by similarity score
        citations.sort(key=lambda c: c.score, reverse=True)
        return citations
