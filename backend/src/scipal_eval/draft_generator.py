import json
import os
from pathlib import Path

from langchain_openai import ChatOpenAI

from backend.domain.config import settings
from backend.rag.ingestion.metadata import Chunk
from backend.storage.sqlite import chunks as chunk_repo

DEFAULT_QUESTION_TYPES: tuple[str, ...] = (
    "summary",
    "method",
    "result",
    "comparison",
    "limitation",
    "definition",
    "evidence",
    "abstention",
)


def generate_draft_dataset(
    session_id: str,
    output_path: Path,
    *,
    max_samples: int = 30,
    question_types: list[str] | None = None,
    use_llm: bool = True,
    generator_model: str = "deepseek-v4-pro",
) -> int:
    """Generate draft samples from stored session chunks."""
    eligible_chunks = [
        chunk
        for chunk in chunk_repo.list_chunks(session_id)
        if len(chunk.text.strip()) >= 40
    ]
    selected_question_types = question_types or ["summary"]
    client = build_generator_client(generator_model) if use_llm else None
    rows: list[dict[str, object]] = []
    for chunk in eligible_chunks:
        for question_type in selected_question_types:
            if len(rows) >= max_samples:
                break
            if client is None:
                row = _build_template_row(
                    session_id=session_id,
                    chunk=chunk,
                    question_type=question_type,
                )
            else:
                row = _build_llm_row(
                    session_id=session_id,
                    chunk=chunk,
                    question_type=question_type,
                    client=client,
                    generator_model=generator_model,
                )
            rows.append(row)
        if len(rows) >= max_samples:
            break
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )
    return len(rows)


def parse_question_types(value: str | None) -> list[str]:
    if value is None or not value.strip():
        return list(DEFAULT_QUESTION_TYPES)
    return [part.strip() for part in value.split(",") if part.strip()]


def build_generator_client(generator_model: str = "deepseek-v4-pro") -> ChatOpenAI:
    api_key = os.environ.get("DEEPSEEK_API_KEY") or settings.deepseek_api_key
    if not api_key:
        raise RuntimeError("generate-draft requires DEEPSEEK_API_KEY, or pass --no-llm to use templates.")
    base_url = os.environ.get("DEEPSEEK_BASE_URL") or settings.deepseek_base_url
    return ChatOpenAI(
        model=generator_model,
        temperature=0,
        api_key=api_key,
        base_url=base_url,
    )


def build_generation_prompt(chunk: Chunk, question_type: str) -> str:
    section = chunk.metadata.section or "Document"
    payload = {
        "question_type": question_type,
        "section": section,
        "chunk_index": chunk.metadata.chunk_index,
        "chunk_text": chunk.text[:1800],
    }
    return (
        "你是 SciPal RAG 评测数据集生成器。"
        "请基于给定论文片段生成一条中文评测 draft 样本。"
        "只输出 JSON，不要输出 Markdown。JSON 字段必须包含："
        "question, reference_answer, answer_requirements, negative_requirements, difficulty, requires_abstention。"
        "difficulty 只能是 easy、medium 或 hard。requires_abstention 是布尔值。\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def parse_generated_row(payload: str) -> dict[str, object]:
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("LLM output must be a JSON object")
    required = {
        "question",
        "reference_answer",
        "answer_requirements",
        "negative_requirements",
        "difficulty",
        "requires_abstention",
    }
    missing = sorted(required.difference(parsed))
    if missing:
        raise ValueError(f"LLM output missing fields: {', '.join(missing)}")
    return parsed


def _build_llm_row(
    session_id: str,
    chunk: Chunk,
    question_type: str,
    client: object,
    generator_model: str,
) -> dict[str, object]:
    try:
        response = client.invoke(build_generation_prompt(chunk, question_type))
        content = getattr(response, "content", response)
        generated = parse_generated_row(str(content))
    except Exception as exc:
        return _build_template_row(
            session_id=session_id,
            chunk=chunk,
            question_type=question_type,
            fallback_error=str(exc),
        )

    row = _build_template_row(
        session_id=session_id,
        chunk=chunk,
        question_type=question_type,
    )
    row.update(
        {
            "question": str(generated["question"]),
            "reference_answer": str(generated["reference_answer"]),
            "answer_requirements": _as_string_list(generated["answer_requirements"]),
            "negative_requirements": _as_string_list(generated["negative_requirements"]),
            "difficulty": str(generated["difficulty"]),
            "requires_abstention": bool(generated["requires_abstention"]),
            "generator": {
                "type": "llm_chunk_question",
                "model": generator_model,
                "source_chunk_indices": [chunk.metadata.chunk_index],
                "question_type": question_type,
            },
        }
    )
    return row


def _as_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _build_row(session_id: str, chunk: Chunk) -> dict[str, object]:
    return _build_template_row(
        session_id=session_id,
        chunk=chunk,
        question_type=_infer_question_type(chunk.metadata.section or "Document"),
    )


def _build_template_row(
    session_id: str,
    chunk: Chunk,
    question_type: str,
    fallback_error: str = "",
) -> dict[str, object]:
    section = chunk.metadata.section or "Document"
    excerpt = chunk.text[:500]
    requires_abstention = question_type == "abstention"
    generator: dict[str, object] = {
        "type": "chunk_template",
        "model": "none",
        "source_chunk_indices": [chunk.metadata.chunk_index],
        "question_type": question_type,
    }
    if fallback_error:
        generator["fallback"] = True
        generator["error"] = fallback_error
    return {
        "sample_id": f"draft-{chunk.metadata.paper_id}-{chunk.metadata.chunk_index}-{question_type}",
        "session_id": session_id,
        "document_id": chunk.metadata.paper_id,
        "question": _template_question(question_type, section, chunk.metadata.chunk_index),
        "reference_answer": (
            "该问题用于测试证据不足时是否拒答；人工审核时应确认论文上下文确实无法回答。"
            if requires_abstention
            else excerpt
        ),
        "expected_contexts": [
            {
                "chunk_index": chunk.metadata.chunk_index,
                "section": section,
                "text": excerpt,
                "relevance_grade": 3,
            }
        ],
        "expected_sections": [section],
        "expected_chunk_indices": [chunk.metadata.chunk_index],
        "expected_evidence_text": [excerpt],
        "expected_citations": [{"section": section, "chunk_index": chunk.metadata.chunk_index}],
        "answer_requirements": _template_answer_requirements(question_type, section),
        "negative_requirements": _template_negative_requirements(question_type),
        "question_type": question_type,
        "difficulty": _template_difficulty(question_type),
        "requires_abstention": requires_abstention,
        "review_status": "draft",
        "generator": generator,
        "notes": "请人工审核 question/reference_answer/expected evidence 后再改为 approved。",
    }


def _template_question(question_type: str, section: str, chunk_index: int) -> str:
    templates = {
        "summary": f"请概括 {section} 章节中 chunk {chunk_index} 的核心内容。",
        "method": f"请说明 {section} 章节中 chunk {chunk_index} 描述的方法主要解决什么问题，关键机制是什么？",
        "result": f"{section} 章节中 chunk {chunk_index} 的结果或发现说明了什么？",
        "comparison": f"{section} 章节中 chunk {chunk_index} 与已有方法、背景或 baseline 相比有什么差异？",
        "limitation": f"根据 {section} 章节中 chunk {chunk_index}，方法有哪些局限或适用条件？",
        "definition": f"请解释 {section} 章节中 chunk {chunk_index} 涉及的关键概念。",
        "evidence": f"请指出 {section} 章节中 chunk {chunk_index} 支持的关键结论和证据。",
        "abstention": f"仅根据 {section} 章节中 chunk {chunk_index}，能否判断论文是否证明了一个未在片段中明确出现的结论？",
    }
    return templates.get(question_type, templates["summary"])


def _template_answer_requirements(question_type: str, section: str) -> list[str]:
    requirements = {
        "summary": [f"必须概括 {section} 章节片段的核心内容"],
        "method": ["必须说明方法目标", "必须说明关键机制"],
        "result": ["必须说明结果或发现", "不得脱离给定片段"],
        "comparison": ["必须说明比较对象", "必须说明差异点"],
        "limitation": ["必须说明局限或适用条件"],
        "definition": ["必须解释关键概念"],
        "evidence": ["必须指出结论", "必须指出支持证据"],
        "abstention": ["必须在证据不足时说明无法从片段判断"],
    }
    return requirements.get(question_type, requirements["summary"])


def _template_negative_requirements(question_type: str) -> list[str]:
    if question_type == "abstention":
        return ["不得编造片段中没有的结论", "不得声称论文已经证明未给出的内容"]
    return ["不得编造论文片段没有的信息", "不得引用不存在的实验或数据"]


def _template_difficulty(question_type: str) -> str:
    if question_type in {"comparison", "limitation", "abstention"}:
        return "hard"
    if question_type in {"method", "result", "evidence"}:
        return "medium"
    return "easy"


def _infer_question_type(section: str) -> str:
    normalized = section.lower()
    if "method" in normalized:
        return "method"
    if "experiment" in normalized:
        return "experiment"
    if "result" in normalized:
        return "result"
    if "limitation" in normalized:
        return "limitation"
    return "background"
