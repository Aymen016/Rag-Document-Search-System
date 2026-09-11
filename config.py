"""
Central config, loaded once from .env. Every other module imports from here
instead of reading os.environ directly, so there's one place to see (and change)
what the whole pipeline is configured to do.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    return default if val is None else val.lower() in ("1", "true", "yes")


# ---- Generation ----
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

# ---- Embeddings ----
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local")
LOCAL_EMBEDDING_MODEL = os.getenv("LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")

# ---- Reranking ----
RERANK_PROVIDER = os.getenv("RERANK_PROVIDER", "local")
LOCAL_RERANK_MODEL = os.getenv("LOCAL_RERANK_MODEL", "BAAI/bge-reranker-base")
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")

# ---- Vector store ----
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")

# ---- Retrieval tuning ----
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "25"))
RERANK_TOP_K = int(os.getenv("RERANK_TOP_K", "5"))
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.15"))

# ---- Chunking ----
MAX_CHUNK_TOKENS = int(os.getenv("MAX_CHUNK_TOKENS", "500"))
CHUNK_OVERLAP_RATIO = float(os.getenv("CHUNK_OVERLAP_RATIO", "0.15"))

# ---- Paths ----
DATA_RAW_DIR = os.getenv("DATA_RAW_DIR", "./data/raw")
DATA_PROCESSED_DIR = os.getenv("DATA_PROCESSED_DIR", "./data/processed")
INGEST_ERROR_LOG = os.getenv("INGEST_ERROR_LOG", "./ingest_errors.log")
