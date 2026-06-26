from typing import TypedDict

from backend.rag.ingestion.metadata import Chunk
from backend.rag.retrieval.filters import filter_indexable_chunks


class ExpansionEntry(TypedDict):
    key: tuple[str, int]
    parent_chunk_index: int
    chunk_index: int
    distance: int


class ExpansionDebugEntry(TypedDict):
    parent_chunk_index: int
    chunk_index: int
    distance: int


def expand_context(
    seed_chunks: list[Chunk],
    all_chunks: list[Chunk],
    max_chunks: int,
    same_section_window: int,
    adjacent_window: int,
    include_linked_blocks: bool,
) -> list[Chunk]:
    expanded_chunks, _ = expand_context_with_debug(
        seed_chunks=seed_chunks,
        all_chunks=all_chunks,
        max_chunks=max_chunks,
        same_section_window=same_section_window,
        adjacent_window=adjacent_window,
        include_linked_blocks=include_linked_blocks,
    )
    return expanded_chunks


def expand_context_with_debug(
    seed_chunks: list[Chunk],
    all_chunks: list[Chunk],
    max_chunks: int,
    same_section_window: int,
    adjacent_window: int,
    include_linked_blocks: bool,
) -> tuple[list[Chunk], list[ExpansionDebugEntry]]:
    filtered_seed_chunks = filter_indexable_chunks(seed_chunks)
    filtered_chunks = filter_indexable_chunks(all_chunks)
    if max_chunks <= 0 or not filtered_seed_chunks:
        return [], []
    if not filtered_chunks:
        return list(filtered_seed_chunks)[:max_chunks], []

    chunk_map = {_chunk_key(chunk): chunk for chunk in filtered_chunks}
    seed_keys = [_chunk_key(chunk) for chunk in filtered_seed_chunks]
    grouped_chunks = _group_chunks_by_document(filtered_chunks)

    linked_entries: list[ExpansionEntry] = []
    same_section_entries: list[ExpansionEntry] = []
    adjacent_entries: list[ExpansionEntry] = []

    for seed in filtered_seed_chunks:
        document_chunks = grouped_chunks.get(seed.metadata.paper_id, [])
        if include_linked_blocks:
            linked_entries.extend(_collect_linked_neighbors(seed, document_chunks))
        same_section_entries.extend(
            _collect_same_section_neighbors(seed, document_chunks, same_section_window)
        )
        adjacent_entries.extend(
            _collect_adjacent_neighbors(seed, document_chunks, adjacent_window)
        )

    selected_keys, expansion_debug = _apply_context_budget(
        chunk_map=chunk_map,
        seed_keys=seed_keys,
        linked_entries=linked_entries,
        same_section_entries=same_section_entries,
        adjacent_entries=adjacent_entries,
        max_chunks=max_chunks,
    )
    return [chunk_map[key] for key in selected_keys if key in chunk_map], expansion_debug


def _chunk_key(chunk: Chunk) -> tuple[str, int]:
    return (chunk.metadata.paper_id, chunk.metadata.chunk_index)


def _section_key(chunk: Chunk) -> tuple[str, ...]:
    section_path = chunk.metadata.section_path
    if section_path:
        return tuple(section_path)
    return (chunk.metadata.section,)


def _group_chunks_by_document(all_chunks: list[Chunk]) -> dict[str, list[Chunk]]:
    grouped: dict[str, list[Chunk]] = {}
    for chunk in sorted(all_chunks, key=_sort_key):
        grouped.setdefault(chunk.metadata.paper_id, []).append(chunk)
    return grouped


def _make_entry(seed: Chunk, chunk: Chunk) -> ExpansionEntry:
    return {
        "key": _chunk_key(chunk),
        "parent_chunk_index": seed.metadata.chunk_index,
        "chunk_index": chunk.metadata.chunk_index,
        "distance": chunk.metadata.chunk_index - seed.metadata.chunk_index,
    }


def _collect_same_section_neighbors(
    seed: Chunk,
    document_chunks: list[Chunk],
    window: int,
) -> list[ExpansionEntry]:
    if window <= 0:
        return []

    candidates = [
        chunk
        for chunk in document_chunks
        if _section_key(chunk) == _section_key(seed)
        and chunk.metadata.chunk_index != seed.metadata.chunk_index
        and abs(chunk.metadata.chunk_index - seed.metadata.chunk_index) <= window
    ]
    candidates.sort(
        key=lambda chunk: (
            abs(chunk.metadata.chunk_index - seed.metadata.chunk_index),
            _sort_key(chunk),
        )
    )
    return [_make_entry(seed, chunk) for chunk in candidates]


def _collect_linked_neighbors(
    seed: Chunk,
    document_chunks: list[Chunk],
) -> list[ExpansionEntry]:
    seed_block_ids = set(seed.metadata.block_ids or [])
    seed_linked_ids = set(seed.metadata.linked_block_ids or [])
    if not seed_block_ids and not seed_linked_ids:
        return []

    neighbors: list[Chunk] = []
    for chunk in document_chunks:
        if chunk.metadata.chunk_index == seed.metadata.chunk_index:
            continue
        candidate_block_ids = set(chunk.metadata.block_ids or [])
        candidate_linked_ids = set(chunk.metadata.linked_block_ids or [])
        is_linked = bool(
            (seed_linked_ids and candidate_block_ids.intersection(seed_linked_ids))
            or (seed_block_ids and candidate_linked_ids.intersection(seed_block_ids))
        )
        if is_linked:
            neighbors.append(chunk)
    return [_make_entry(seed, chunk) for chunk in sorted(neighbors, key=_sort_key)]


def _collect_adjacent_neighbors(
    seed: Chunk,
    document_chunks: list[Chunk],
    window: int,
) -> list[ExpansionEntry]:
    if window <= 0:
        return []

    chunk_by_key = {_chunk_key(chunk): chunk for chunk in document_chunks}
    neighbors = [
        _make_entry(seed, chunk)
        for chunk in document_chunks
        if chunk.metadata.chunk_index != seed.metadata.chunk_index
        and abs(chunk.metadata.chunk_index - seed.metadata.chunk_index) <= window
    ]
    neighbors.sort(
        key=lambda entry: (
            abs(entry["distance"]),
            _sort_key(chunk_by_key[entry["key"]]),
        )
    )
    return neighbors


def _apply_context_budget(
    chunk_map: dict[tuple[str, int], Chunk],
    seed_keys: list[tuple[str, int]],
    linked_entries: list[ExpansionEntry],
    same_section_entries: list[ExpansionEntry],
    adjacent_entries: list[ExpansionEntry],
    max_chunks: int,
) -> tuple[list[tuple[str, int]], list[ExpansionDebugEntry]]:
    selected: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    selected_expansion_keys: list[tuple[str, int]] = []
    expansion_debug_by_key: dict[tuple[str, int], ExpansionDebugEntry] = {}

    for key in seed_keys:
        if key in seen:
            continue
        selected.append(key)
        seen.add(key)

    for entry in [*linked_entries, *same_section_entries, *adjacent_entries]:
        key = entry["key"]
        if key in seen or len(selected) >= max_chunks:
            continue
        selected.append(key)
        seen.add(key)
        selected_expansion_keys.append(key)
        expansion_debug_by_key[key] = {
            "parent_chunk_index": entry["parent_chunk_index"],
            "chunk_index": entry["chunk_index"],
            "distance": entry["distance"],
        }

    seeds = [key for key in selected if key in seed_keys]
    extras = [key for key in selected if key not in seed_keys]
    extras_sorted = sorted(extras, key=lambda key: _sort_key(chunk_map[key]))
    budget = max(max_chunks - len(seeds), 0)
    final_extra_keys = extras_sorted[:budget]
    final_keys = sorted(seeds + final_extra_keys, key=lambda key: _sort_key(chunk_map[key]))
    final_extra_key_set = set(final_extra_keys)
    final_debug = [
        expansion_debug_by_key[key]
        for key in selected_expansion_keys
        if key in final_extra_key_set
    ]
    return final_keys, final_debug
def _sort_key(chunk: Chunk) -> tuple[str, int, int]:
    return (
        chunk.metadata.paper_id,
        chunk.metadata.page_start if chunk.metadata.page_start is not None else -1,
        chunk.metadata.chunk_index,
    )
