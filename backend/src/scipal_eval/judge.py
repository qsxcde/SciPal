import json
import os

from langchain_openai import ChatOpenAI

from backend.domain.config import settings
from scipal_eval.models import EvalSample
from scipal_eval.models import EvalSampleResult
from scipal_eval.models import JudgeMetricBundle


def build_judge_client(judge_model: str = "deepseek-v4-pro") -> ChatOpenAI:
  api_key = os.environ.get("DEEPSEEK_API_KEY") or settings.deepseek_api_key
  if not api_key:
    raise RuntimeError("LLM-Judge requires DEEPSEEK_API_KEY to be configured.")
  base_url = os.environ.get("DEEPSEEK_BASE_URL") or settings.deepseek_base_url
  model = os.environ.get("SCIPAL_EVAL_JUDGE_MODEL") or judge_model
  return ChatOpenAI(
    model=model,
    temperature=0,
    api_key=api_key,
    base_url=base_url,
  )


def build_judge_prompt(sample: EvalSample, result: EvalSampleResult) -> str:
  payload = {
    "question": sample.question,
    "reference_answer": sample.reference_answer,
    "answer": result.generated_answer,
    "retrieved_contexts": result.retrieved_contexts,
    "sources": result.sources,
    "expected_citations": [citation.model_dump(mode="json") for citation in sample.expected_citations],
    "answer_requirements": sample.answer_requirements,
    "negative_requirements": sample.negative_requirements,
    "requires_abstention": sample.requires_abstention,
  }
  return (
    "你是 SciPal RAG 回归评测的严格裁判。"
    "请根据给定问题、参考答案、检索上下文、模型回答和来源，评估回答质量。"
    "只输出 JSON，不要输出 Markdown。JSON 字段必须包含："
    "completeness, citation_accuracy, hallucination_rate, task_success_rate, "
    "end_to_end_answer_quality, abstention_accuracy, rationale。"
    "所有分数使用 0 到 1，hallucination_rate 也是 0 到 1，越低越好。\n\n"
    f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
  )


def parse_judge_response(payload: str) -> JudgeMetricBundle:
  data = json.loads(_strip_markdown_fence(payload))
  return JudgeMetricBundle(
    completeness=_safe_score(data.get("completeness")),
    citation_accuracy=_safe_score(data.get("citation_accuracy")),
    hallucination_rate=_safe_score(data.get("hallucination_rate")),
    task_success_rate=_safe_score(data.get("task_success_rate")),
    end_to_end_answer_quality=_safe_score(data.get("end_to_end_answer_quality")),
    abstention_accuracy=_safe_score(data.get("abstention_accuracy")),
    rationale=str(data.get("rationale") or ""),
  )


def score_judge_metrics(
  samples: list[EvalSample],
  results: list[EvalSampleResult],
  *,
  judge_model: str = "deepseek-v4-pro",
) -> list[EvalSampleResult]:
  samples_by_id = {sample.sample_id: sample for sample in samples}
  client = build_judge_client(judge_model)
  for result in results:
    if result.status != "complete":
      continue
    sample = samples_by_id.get(result.sample_id)
    if sample is None:
      continue
    prompt = build_judge_prompt(sample, result)
    try:
      response = client.invoke(prompt)
      content = getattr(response, "content", response)
      result.judge_metrics = parse_judge_response(str(content))
    except Exception as exc:
      result.judge_warning = str(exc)
  return results


def _safe_score(value: object) -> float | None:
  if value is None:
    return None
  try:
    parsed = float(value)
  except (TypeError, ValueError):
    return None
  if parsed < 0:
    return 0.0
  if parsed > 1:
    return 1.0
  return parsed


def _strip_markdown_fence(payload: str) -> str:
  cleaned = payload.strip()
  if not cleaned.startswith("```"):
    return cleaned
  first_newline = cleaned.find("\n")
  if first_newline == -1:
    return cleaned.strip("`").strip()
  cleaned = cleaned[first_newline + 1 :]
  if cleaned.endswith("```"):
    cleaned = cleaned[:-3]
  return cleaned.strip()
