"""
RAG Retrieval Tool - Uses ChromaDB with ONNX embeddings for document retrieval.
"""

import os
import logging
from mcp.server.fastmcp import FastMCP
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

logger = logging.getLogger(__name__)

# Global reference to ChromaDB collection
_chroma_collection = None


def set_chroma_collection(collection):
    """Set the ChromaDB collection for RAG queries."""
    global _chroma_collection
    _chroma_collection = collection


async def fetch_rag_query(query: str, collection_name: str = "medical_knowledge", n_results: int = 3) -> str:
    """Execute RAG query against ChromaDB knowledge base."""
    global _chroma_collection

    if _chroma_collection is None:
        try:
            import chromadb
            persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "/data/chromadb")
            embedding_fn = ONNXMiniLM_L6_V2()
            client = chromadb.PersistentClient(path=persist_dir)
            _chroma_collection = client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
                embedding_function=embedding_fn,
            )
        except Exception as e:
            logger.error(f"Failed to connect to ChromaDB: {e}")
            return (
                "Knowledge base is not available. The vector database could not be loaded. "
                "Please ensure the system is properly initialized."
            )

    try:
        count = _chroma_collection.count()
        if count == 0:
            return (
                "The knowledge base is currently empty. No documents have been indexed yet."
            )

        results = _chroma_collection.query(
            query_texts=[query],
            n_results=min(n_results, count),
            include=["documents", "metadatas", "distances"],
        )

        if not results["documents"] or not results["documents"][0]:
            return f"No relevant information found for: {query}"

        passages = []
        passages.append(f"📚 Knowledge Base Results for: \"{query}\"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

        for i, (doc, metadata, distance) in enumerate(
            zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ),
            1,
        ):
            source = metadata.get("source", "Knowledge Base")
            section = metadata.get("section", "")
            relevance = round((1.0 - float(distance)) * 100, 1)

            passages.append(
                f"📄 Passage {i} (Relevance: {relevance}%)\n"
                f"   Source: {source}"
                + (f" | Section: {section}" if section else "")
                + f"\n   {doc}\n"
            )

        return "\n".join(passages)

    except Exception as e:
        logger.error(f"RAG query error: {e}")
        return f"Error querying knowledge base: {str(e)}"


def register_rag_tools(mcp: FastMCP):
    """Register RAG tool with FastMCP."""
    @mcp.tool()
    async def rag_query(query: str, collection_name: str = "medical_knowledge", n_results: int = 3) -> str:
        """
        Query the domain knowledge base using RAG (Retrieval Augmented Generation).
        Searches through locally stored vector documents.

        Args:
            query: The question or search query
            collection_name: Target collection (default: 'medical_knowledge')
            n_results: Max passages to return (default: 3)
        """
        return await fetch_rag_query(query, collection_name, n_results)
