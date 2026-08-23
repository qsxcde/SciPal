import logging

from backend.rag.ingestion.document_ir import BBox

logger = logging.getLogger(__name__)


def bbox_tuple(value: object) -> tuple[float, float, float, float]:
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
    logger.warning("Invalid bbox value: %r, falling back to (0,0,0,0)", value)
    return (0.0, 0.0, 0.0, 0.0)


def is_page_margin_block(bbox: BBox, page_height: float) -> bool:
    if page_height <= 0:
        return False
    return bbox.y1 <= page_height * 0.1 or bbox.y0 >= page_height * 0.9


def sorted_blocks_for_reading_order(
    blocks: list[dict],
    page_width: float,
    bbox_model,
) -> list[dict]:
    # Keep formula blocks even when they have no text
    filtered = [
        block for block in blocks
        if str(block.get("text", "")).strip()
        or str(block.get("type", "")).strip().lower() in {"formula"}
    ]
    if looks_like_two_column_layout(filtered, page_width, bbox_model):
        gap = _column_gap(filtered, page_width, bbox_model)
        left_blocks = [block for block in filtered if bbox_model(block.get("bbox")).x0 < gap]
        right_blocks = [block for block in filtered if bbox_model(block.get("bbox")).x0 >= gap]
        return sort_single_column(left_blocks, bbox_model) + sort_single_column(right_blocks, bbox_model)
    return sort_single_column(filtered, bbox_model)


def _bbox_sort_key(item: dict, bbox_model) -> tuple[float, float]:
    bbox = bbox_model(item.get("bbox"))
    if hasattr(bbox, "y0"):
        return (bbox.y0, bbox.x0)
    return (bbox[1], bbox[0])


def sort_single_column(blocks: list[dict], bbox_model=None) -> list[dict]:
    model = bbox_model or bbox_tuple
    return sorted(blocks, key=lambda item: _bbox_sort_key(item, model))


def _column_gap(blocks: list[dict], page_width: float, bbox_model) -> float:
    """Find natural column gap using block midpoints."""
    midpoints = sorted({(bbox_model(b.get("bbox")).x0 + bbox_model(b.get("bbox")).x1) / 2 for b in blocks})
    if len(midpoints) < 3:
        return page_width / 2
    gaps = [(midpoints[i + 1] - midpoints[i]) for i in range(len(midpoints) - 1)]
    largest_idx = gaps.index(max(gaps))
    if gaps[largest_idx] > page_width * 0.05:
        return (midpoints[largest_idx] + midpoints[largest_idx + 1]) / 2
    return page_width / 2


def looks_like_two_column_layout(
    blocks: list[dict],
    page_width: float,
    bbox_model,
) -> bool:
    if page_width <= 0 or len(blocks) < 4:
        return False
    midpoint = page_width / 2
    left = [block for block in blocks if bbox_model(block.get("bbox")).x0 < midpoint]
    right = [block for block in blocks if bbox_model(block.get("bbox")).x0 >= midpoint]
    if len(left) < 2 or len(right) < 2:
        return False
    left_span = max(bbox_model(block.get("bbox")).x1 for block in left)
    right_span = min(bbox_model(block.get("bbox")).x0 for block in right)
    return left_span < right_span
