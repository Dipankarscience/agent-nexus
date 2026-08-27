"""
Vector Store Loader - Loads documents, chunks them, and stores in ChromaDB
using ONNX Runtime for all-MiniLM-L6-v2 embeddings (lightweight, no PyTorch needed).
"""

import os
import logging
import glob

import chromadb
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

logger = logging.getLogger(__name__)

PERSIST_DIR = os.environ.get("CHROMA_PERSIST_DIR", "/data/chromadb")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    sentences = text.replace("\n\n", "\n").split("\n")
    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(current_chunk) + len(sentence) + 1 > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            words = current_chunk.split()
            overlap_words = words[-overlap:] if len(words) > overlap else words
            current_chunk = " ".join(overlap_words) + " " + sentence
        else:
            current_chunk = current_chunk + " " + sentence if current_chunk else sentence

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def load_documents(data_dir: str) -> list[dict]:
    """Load all text documents from the data directory."""
    documents = []
    txt_files = glob.glob(os.path.join(data_dir, "**", "*.txt"), recursive=True)

    for filepath in txt_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            filename = os.path.basename(filepath)
            rel_path = os.path.relpath(filepath, data_dir)
            parts = rel_path.split(os.sep)
            category = parts[0] if len(parts) > 1 else "general"

            documents.append({
                "content": content,
                "source": filename,
                "category": category,
                "path": rel_path,
            })
            logger.info(f"Loaded document: {rel_path}")
        except Exception as e:
            logger.warning(f"Failed to load {filepath}: {e}")

    return documents


async def initialize_vectorstore():
    """Initialize ChromaDB with ONNX embeddings and index documents."""
    logger.info(f"Initializing ONNX vector store at: {PERSIST_DIR}")

    # Use ChromaDB's ONNX-based embedding function (all-MiniLM-L6-v2)
    # This runs directly on ONNX Runtime without PyTorch
    embedding_fn = ONNXMiniLM_L6_V2()

    # Create ChromaDB persistent client
    client = chromadb.PersistentClient(path=PERSIST_DIR)

    # Create or get collection with ONNX embedding function
    collection = client.get_or_create_collection(
        name="medical_knowledge",
        metadata={"hnsw:space": "cosine"},
        embedding_function=embedding_fn,
    )

    # Check if already populated
    existing_count = collection.count()
    if existing_count > 0:
        logger.info(f"Vector store already contains {existing_count} documents. Skipping re-indexing.")
        from app.tools.rag_tool import set_chroma_collection
        set_chroma_collection(collection)
        return

    # Load documents from data directory
    documents = load_documents(DATA_DIR)
    if not documents:
        logger.warning(f"No documents found in {DATA_DIR}. Vector store initialized empty.")
        from app.tools.rag_tool import set_chroma_collection
        set_chroma_collection(collection)
        return

    # Chunk and index documents
    all_chunks = []
    all_metadatas = []
    all_ids = []

    for doc in documents:
        chunks = chunk_text(doc["content"])
        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            all_metadatas.append({
                "source": doc["source"],
                "category": doc["category"],
                "section": f"chunk_{i + 1}",
            })
            all_ids.append(f"{doc['source']}_{i}")

    if all_chunks:
        # Index in batches
        batch_size = 100
        for i in range(0, len(all_chunks), batch_size):
            batch_end = min(i + batch_size, len(all_chunks))
            collection.add(
                documents=all_chunks[i:batch_end],
                metadatas=all_metadatas[i:batch_end],
                ids=all_ids[i:batch_end],
            )
        logger.info(f"Successfully indexed {len(all_chunks)} chunks via ONNX runtime.")

    # Register collection in RAG tool
    from app.tools.rag_tool import set_chroma_collection
    set_chroma_collection(collection)
