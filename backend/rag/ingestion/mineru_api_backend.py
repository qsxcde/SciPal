import io
import json
import logging
import time
import zipfile
from typing import Any

import httpx

from backend.domain.config import settings
from backend.rag.ingestion.parser_backend import RawParserResult

logger = logging.getLogger(__name__)

# MinerU Cloud API limits
API_MAX_FILE_BYTES = 200 * 1024 * 1024  # 200 MB


class MinerUApiBackend:
    name = "mineru_api"
    version = "1.0"

    def __init__(self) -> None:
        self.base_url = settings.mineru_api_base_url.rstrip("/")
        self.api_key = settings.mineru_api_key
        self.http_timeout = settings.mineru_api_timeout
        self.poll_interval = settings.mineru_api_poll_interval
        self.max_poll_time = settings.mineru_api_max_poll_time

    def parse(self, pdf_bytes: bytes, filename: str | None = None) -> RawParserResult:
        if len(pdf_bytes) > API_MAX_FILE_BYTES:
            raise RuntimeError(
                f"PDF ({len(pdf_bytes)} bytes) exceeds MinerU API limit ({API_MAX_FILE_BYTES} bytes)"
            )

        logger.info("MinerU API parse start filename=%s bytes=%d", filename or "?", len(pdf_bytes))
        with httpx.Client(timeout=self.http_timeout) as client:
            batch_id = self._upload_file(client, pdf_bytes, filename)
            result_url = self._poll_batch(client, batch_id)
            result = self._process_result(client, result_url)
        logger.info("MinerU API parse succeeded filename=%s pages=%d", filename or "?", result.page_count)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def __repr__(self) -> str:
        return f"MinerUApiBackend(base_url={self.base_url})"

    def _upload_file(self, client: httpx.Client, pdf_bytes: bytes, filename: str | None) -> str:
        """Request signed upload URL, upload binary, return batch_id.

        The MinerU API auto-submits the extraction task after the PUT
        completes — no separate submit call is needed.
        """
        url = f"{self.base_url}/api/v4/file-urls/batch"
        payload: dict[str, object] = {
            "files": [{"name": filename or "document.pdf"}],
            "model_version": "vlm",
            "enable_formula": True,
            "enable_table": True,
        }
        resp = client.post(url, json=payload, headers=self._auth_header())
        resp.raise_for_status()
        body = resp.json()
        self._assert_ok(body, "get upload url")

        batch_id: str = body["data"]["batch_id"]
        signed_urls: list[str] = body["data"]["file_urls"]

        upload_resp = client.put(signed_urls[0], content=pdf_bytes)
        upload_resp.raise_for_status()

        logger.info("File uploaded batch_id=%s", batch_id)
        return batch_id

    def _poll_batch(self, client: httpx.Client, batch_id: str) -> str:
        """Poll batch results until done, return the result ZIP download URL."""
        url = f"{self.base_url}/api/v4/extract-results/batch/{batch_id}"
        deadline = time.monotonic() + self.max_poll_time

        while time.monotonic() < deadline:
            resp = client.get(url, headers=self._auth_header())
            resp.raise_for_status()
            body = resp.json()
            self._assert_ok(body, "poll task")

            results = body["data"].get("extract_result", [])
            if not results:
                time.sleep(self.poll_interval)
                continue

            state = results[0].get("state", "pending")
            if state == "done":
                return results[0]["full_zip_url"]
            if state == "failed":
                reason = results[0].get("err_msg", "unknown error")
                raise RuntimeError(f"MinerU API task failed: {reason}")

            time.sleep(self.poll_interval)

        raise TimeoutError(
            f"MinerU API batch {batch_id} did not complete within {self.max_poll_time}s"
        )

    def _process_result(self, client: httpx.Client, result_url: str) -> RawParserResult:
        """Download result ZIP and map to RawParserResult.

        The Cloud API v4 result ZIP contains:
          - full.md                      — main markdown
          - {uuid}_content_list_v2.json   — page-grouped content blocks
          - {uuid}_content_list.json      — flat content list (fallback)
          - layout.json                   — full intermediate result (page dimensions)
          - {uuid}_model.json, images/... — supplementary
        """
        resp = client.get(result_url)
        resp.raise_for_status()

        raw = resp.content
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            full_md = zf.read("full.md").decode("utf-8") if "full.md" in names else ""

            pages = self._parse_zip_content(zf, names)

        metadata = {"source": "mineru_api"}
        return RawParserResult(
            markdown=full_md,
            page_count=len(pages),
            pages=pages,
            metadata=metadata,
            source_parser=self.name,
        )

    def _parse_zip_content(
        self, zf: zipfile.ZipFile, names: list[str]
    ) -> list[dict[str, Any]]:
        """Extract page blocks from the result ZIP, trying multiple format variants."""
        # Page dimensions from layout.json (if available)
        page_sizes: dict[int, tuple[float, float]] = {}
        if "layout.json" in names:
            try:
                layout = json.loads(zf.read("layout.json"))
                for page_info in layout.get("pdf_info", []):
                    idx = page_info.get("page_idx")
                    size = page_info.get("page_size")
                    if idx is not None and isinstance(size, (list, tuple)) and len(size) >= 2:
                        page_sizes[int(idx)] = (float(size[0]), float(size[1]))
            except Exception:
                pass

        # 1. Prefer content_list_v2.json (page-grouped format)
        cl_v2_name = next((n for n in names if "content_list_v2.json" in n), None)
        if cl_v2_name:
            try:
                data = json.loads(zf.read(cl_v2_name))
                return self._map_pages_from_cl_v2(data, page_sizes)
            except Exception:
                logger.warning("Failed to parse %s, falling back", cl_v2_name)

        # 2. Fall back to content_list.json (flat format)
        cl_v1_name = next((n for n in names if "content_list.json" in n and "v2" not in n), None)
        if cl_v1_name:
            try:
                data = json.loads(zf.read(cl_v1_name))
                return self._map_pages_from_cl_v1(data, page_sizes)
            except Exception:
                logger.warning("Failed to parse %s, falling back", cl_v1_name)

        # 3. Fall back to content.json (legacy local MinerU format)
        if "content.json" in names:
            try:
                content = json.loads(zf.read("content.json"))
                return self._map_pages(content, page_sizes)
            except Exception:
                logger.warning("Failed to parse content.json")

        logger.warning("No parseable content file found in result ZIP")
        return []

    # ------------------------------------------------------------------
    # Output mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_pages_from_cl_v2(
        data: list[list[dict[str, Any]]],
        page_sizes: dict[int, tuple[float, float]],
    ) -> list[dict[str, Any]]:
        """Map content_list_v2.json (page-grouped array) to normalizer page format."""
        pages: list[dict[str, Any]] = []
        for page_idx, page_items in enumerate(data):
            width, height = page_sizes.get(page_idx, (0.0, 0.0))
            blocks: list[dict[str, Any]] = []

            for item in page_items:
                mapped = _map_block_from_v2(item)
                if mapped is not None:
                    blocks.append(mapped)

            pages.append({
                "page_number": page_idx + 1,
                "width": width,
                "height": height,
                "blocks": blocks,
            })
        return pages

    @staticmethod
    def _map_pages_from_cl_v1(
        data: list[dict[str, Any]],
        page_sizes: dict[int, tuple[float, float]],
    ) -> list[dict[str, Any]]:
        """Map content_list.json (flat array) to normalizer page format."""
        page_map: dict[int, list[dict[str, Any]]] = {}
        for item in data:
            page_idx = item.get("page_idx", 0)
            mapped = _map_block_from_v1(item)
            if mapped is not None:
                page_map.setdefault(page_idx, []).append(mapped)

        if not page_map:
            return []

        max_page = max(page_map.keys())
        pages: list[dict[str, Any]] = []
        for i in range(max_page + 1):
            width, height = page_sizes.get(i, (0.0, 0.0))
            pages.append({
                "page_number": i + 1,
                "width": width,
                "height": height,
                "blocks": page_map.get(i, []),
            })
        return pages

    @staticmethod
    def _map_pages(content: dict[str, Any], page_sizes: dict[int, tuple[float, float]]) -> list[dict[str, Any]]:
        """Map legacy content.json pages into the format the normalizer expects (fallback)."""
        pages: list[dict[str, Any]] = []
        for i, page_data in enumerate(content.get("pages", [])):
            page_number = int(page_data.get("page_number", i + 1))
            width, height = page_sizes.get(i, (float(page_data.get("width", 0.0)), float(page_data.get("height", 0.0))))

            raw_blocks: list[dict[str, Any]] = (
                page_data.get("page_blocks") or page_data.get("blocks") or []
            )
            blocks = [_map_block(b) for b in raw_blocks]

            pages.append({
                "page_number": page_number,
                "width": width,
                "height": height,
                "blocks": blocks,
            })
        return pages

    @staticmethod
    def _assert_ok(body: dict[str, Any], stage: str) -> None:
        if body.get("code") != 0:
            raise RuntimeError(
                f"MinerU API error at {stage}: code={body.get('code')}, msg={body.get('msg', 'unknown')}"
            )


# ------------------------------------------------------------------
# Block mapping helpers
# ------------------------------------------------------------------


def _map_block(block: dict[str, Any]) -> dict[str, Any]:
    """Map a legacy content.json block to the format the normalizer expects."""
    mapped: dict[str, Any] = {
        "type": block.get("type", "paragraph"),
        "text": block.get("text", ""),
        "bbox": block.get("bbox", [0.0, 0.0, 0.0, 0.0]),
    }
    if "confidence" in block:
        mapped["confidence"] = block["confidence"]
    links = block.get("links")
    if links:
        mapped["links"] = links
    return mapped


def _concat_fragments(fragments: list[Any]) -> str:
    """Concatenate content fragments (e.g. [{'type':'text','content':'...'}, ...]) into a single string."""
    parts: list[str] = []
    if isinstance(fragments, list):
        for frag in fragments:
            if isinstance(frag, dict):
                text = frag.get("content", "")
                if text:
                    parts.append(str(text))
                children = frag.get("children")
                if children:
                    parts.append(_concat_fragments(children))
    return "".join(parts)


# Map from content_list_v2 types to normalizer block types
_V2_TYPE_MAP: dict[str, str] = {
    "title": "title",
    "paragraph": "paragraph",
    "equation_interline": "formula",
    "page_footnote": "footnote",
    "page_aside_text": "aside_text",
}


def _map_block_from_v2(item: dict[str, Any]) -> dict[str, Any] | None:
    """Map a content_list_v2.json block to the format the normalizer expects.

    Returns None for visual-only blocks that should be skipped.
    """
    raw_type = item.get("type", "")
    norm_type = _V2_TYPE_MAP.get(raw_type, raw_type)
    bbox = item.get("bbox", [0.0, 0.0, 0.0, 0.0])
    content = item.get("content", {})

    text = ""
    if raw_type == "title":
        text = _concat_fragments(content.get("title_content", []))
    elif raw_type == "paragraph":
        text = _concat_fragments(content.get("paragraph_content", []))
    elif raw_type == "equation_interline":
        text = content.get("math_content", "")
    elif raw_type == "image":
        captions = content.get("image_caption", [])
        text = _concat_fragments(captions)
        if not text:
            return None
        norm_type = "figure_caption"
    elif raw_type == "chart":
        captions = content.get("chart_caption", [])
        text = _concat_fragments(captions)
        if not text:
            return None
        norm_type = "figure_caption"
    elif raw_type == "table":
        captions = content.get("table_caption", [])
        text = _concat_fragments(captions)
        norm_type = "table"
    elif raw_type == "list":
        items = content.get("list_items", [])
        texts: list[str] = []
        for li in items:
            if isinstance(li, dict):
                item_text = _concat_fragments(li.get("item_content", []))
                if item_text:
                    texts.append(item_text)
        text = "\n".join(texts)
        norm_type = "paragraph"
    elif raw_type == "page_aside_text":
        text = _concat_fragments(content.get("page_aside_text_content", []))
    elif raw_type == "page_footnote":
        text = _concat_fragments(content.get("page_footnote_content", []))

    text = text.strip()
    if not text:
        return None

    return {
        "type": norm_type,
        "text": text,
        "bbox": bbox,
    }


def _map_block_from_v1(item: dict[str, Any]) -> dict[str, Any] | None:
    """Map a content_list.json (v1) block to the format the normalizer expects."""
    raw_type = item.get("type", "")
    text = item.get("text", "").strip()
    bbox = item.get("bbox", [0.0, 0.0, 0.0, 0.0])

    if not text and raw_type not in {"equation", "table"}:
        return None

    # Map types
    if raw_type == "text":
        text_level = item.get("text_level", 0)
        norm_type = "title" if text_level >= 1 else "paragraph"
    elif raw_type == "equation":
        norm_type = "formula"
    elif raw_type == "table":
        norm_type = "table"
    elif raw_type == "image":
        norm_type = "figure_caption"
    elif raw_type == "chart":
        norm_type = "figure_caption"
    elif raw_type == "aside_text":
        norm_type = "aside_text"
    elif raw_type == "page_footnote":
        norm_type = "footnote"
    else:
        norm_type = raw_type

    return {
        "type": norm_type,
        "text": text,
        "bbox": bbox,
    }
