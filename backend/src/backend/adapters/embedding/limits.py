"""Input limits shared by the embedding backends and ingestion budgeting.

Kept dependency-free so ingestion code can reason about the cap without
importing torch / sentence-transformers.
"""

MAX_EMBEDDING_WORDS = 220
MAX_EMBEDDING_CHARS = 1600
