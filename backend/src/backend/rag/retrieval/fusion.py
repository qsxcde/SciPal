from __future__ import annotations

from dataclasses import dataclass

from backend.rag.ingestion.metadata import Chunk


@dataclass(frozen=True)
class RetrievalHit:
    chunk: Chunk
    rank: int
    score: float


@dataclass
class RankedCandidate:
    chunk: Chunk
    fused_score: float
    retrieval_rank: int
    channels: list[str]
    channel_ranks: dict[str, int]

    def to_debug_dict(self) -> dict[str, object]:
        ordered_channel_ranks = {channel: self.channel_ranks[channel] for channel in self.channels}
        return {
            "paper_id": self.chunk.metadata.paper_id,
            "chunk_index": self.chunk.metadata.chunk_index,
            "fused_score": round(self.fused_score, 8),
            "retrieval_rank": self.retrieval_rank,
            "channels": list(self.channels),
            "channel_ranks": ordered_channel_ranks,
        }


def reciprocal_rank_fusion(
    channels: dict[str, list[RetrievalHit]],
    *,
    top_k: int,
    rrf_k: int = 60,
) -> list[RankedCandidate]:
    fused: dict[tuple[str, int], RankedCandidate] = {}

    for channel_name in sorted(channels):
        hits = channels[channel_name]
        best_hits: dict[tuple[str, int], RetrievalHit] = {}
        for hit in hits:
            identity = _chunk_identity(hit.chunk)
            previous = best_hits.get(identity)
            if previous is None or hit.rank < previous.rank:
                best_hits[identity] = hit

        for identity, hit in best_hits.items():
            candidate = fused.get(identity)
            if candidate is None:
                candidate = RankedCandidate(
                    chunk=hit.chunk,
                    fused_score=0.0,
                    retrieval_rank=0,
                    channels=[],
                    channel_ranks={},
                )
                fused[identity] = candidate

            candidate.fused_score += 1 / (rrf_k + hit.rank)
            candidate.channel_ranks[channel_name] = hit.rank
            candidate.channels.append(channel_name)

    ranked = sorted(
        fused.values(),
        key=lambda candidate: (
            -candidate.fused_score,
            candidate.chunk.metadata.paper_id,
            candidate.chunk.metadata.chunk_index,
        ),
    )

    for rank, candidate in enumerate(ranked[:top_k], start=1):
        candidate.retrieval_rank = rank

    return ranked[:top_k]


def _chunk_identity(chunk: Chunk) -> tuple[str, int]:
    return (chunk.metadata.paper_id, chunk.metadata.chunk_index)
