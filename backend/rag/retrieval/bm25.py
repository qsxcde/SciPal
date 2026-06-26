from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import re

from backend.rag.ingestion.metadata import Chunk
from backend.rag.retrieval.filters import filter_indexable_chunks


_TOKEN_PATTERN = re.compile(r"\d+(?:\.\d+)+|\d+|[a-z]+[a-z0-9]*")


@dataclass(frozen=True, slots=True)
class BM25SearchResult:
    chunk: Chunk
    score: float
    rank: int


def tokenize_for_bm25(text: str) -> list[str]:
    normalized = text.lower()
    tokens = _TOKEN_PATTERN.findall(normalized)
    cjk_blocks = re.findall(r"[\u4e00-\u9fff]+", text)
    for block in cjk_blocks:
        tokens.extend(block)
        tokens.extend(block[i : i + 2] for i in range(len(block) - 1))
    return tokens


class BM25Retriever:
    def __init__(self, chunks: list[Chunk], *, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b

        unique_chunks: list[Chunk] = []
        seen_identities: set[tuple[str, int]] = set()
        for chunk in filter_indexable_chunks(chunks):
            identity = (chunk.metadata.paper_id, chunk.metadata.chunk_index)
            if identity in seen_identities:
                continue
            seen_identities.add(identity)
            unique_chunks.append(chunk)

        self._chunks = unique_chunks
        self._tokenized_chunks = [tokenize_for_bm25(chunk.text) for chunk in self._chunks]
        self._term_frequencies = [Counter(tokens) for tokens in self._tokenized_chunks]
        self._doc_lengths = [len(tokens) for tokens in self._tokenized_chunks]
        self._avg_doc_length = (
            sum(self._doc_lengths) / len(self._doc_lengths) if self._doc_lengths else 0.0
        )

        self._doc_frequencies: Counter[str] = Counter()
        for frequencies in self._term_frequencies:
            self._doc_frequencies.update(frequencies.keys())

    def search(self, query: str, k: int = 5) -> list[BM25SearchResult]:
        if not self._chunks or k <= 0:
            return []

        query_tokens = tokenize_for_bm25(query)
        if not query_tokens:
            return []

        results: list[tuple[Chunk, float]] = []
        total_docs = len(self._chunks)

        for chunk, frequencies, doc_length in zip(
            self._chunks,
            self._term_frequencies,
            self._doc_lengths,
            strict=True,
        ):
            score = 0.0
            for token in query_tokens:
                term_frequency = frequencies.get(token, 0)
                if term_frequency == 0:
                    continue

                doc_frequency = self._doc_frequencies[token]
                idf = math.log(1.0 + (total_docs - doc_frequency + 0.5) / (doc_frequency + 0.5))
                length_norm = 1.0 - self._b + self._b * doc_length / self._avg_doc_length
                numerator = term_frequency * (self._k1 + 1.0)
                denominator = term_frequency + self._k1 * length_norm
                score += idf * numerator / denominator

            if score > 0:
                results.append((chunk, score))

        results.sort(
            key=lambda item: (
                -item[1],
                item[0].metadata.paper_id,
                item[0].metadata.chunk_index,
            )
        )

        ranked_results: list[BM25SearchResult] = []
        for rank, (chunk, score) in enumerate(results[:k], start=1):
            ranked_results.append(BM25SearchResult(chunk=chunk, score=score, rank=rank))
        return ranked_results
