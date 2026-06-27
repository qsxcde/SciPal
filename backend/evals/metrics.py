import math
import os
from typing import TypeVar

from langchain_openai import ChatOpenAI

from backend.domain.config import settings
from backend.evals.models import (
  EvalSample,
  EvalSampleResult,
  RagasMetricBundle,
  RetrievalMetricBundle,
)
from backend.evals.ragas_eval import build_single_turn_samples


T = TypeVar("T")


def calculate_retrieval_metrics(
  sample: EvalSample,
  result: EvalSampleResult,
) -> RetrievalMetricBundle:
  """Calculate deterministic retrieval metrics from expected and retrieved labels."""
  expected_chunks = _expected_chunk_keys(sample)
  retrieved_chunks = _result_chunk_keys(sample, result)
  ranked_chunks = _result_chunk_keys(sample, result, ranked=True)
  expected_sections = _expected_section_keys(sample)
  retrieved_sections = _result_section_keys(sample, result)

  matched_chunks = expected_chunks.intersection(set(retrieved_chunks))
  matched_sections = expected_sections.intersection(set(retrieved_sections))

  return RetrievalMetricBundle(
    chunk_hit_rate=1.0 if matched_chunks else 0.0,
    chunk_recall=_safe_recall(len(matched_chunks), len(expected_chunks)),
    section_hit_rate=1.0 if matched_sections else 0.0,
    section_recall=_safe_recall(len(matched_sections), len(expected_sections)),
    mrr=None if sample.requires_abstention else _calculate_mrr(ranked_chunks, expected_chunks),
    recall_at_k=None if sample.requires_abstention else _calculate_recall_at_k(sample, ranked_chunks),
    ndcg_at_k=None if sample.requires_abstention else _calculate_ndcg_at_k(sample, ranked_chunks),
    retrieved_context_count=len(result.retrieved_contexts),
    empty_retrieval=len(result.retrieved_contexts) == 0,
    token_budget_proxy=sum(len(context) for context in result.retrieved_contexts),
  )


def _expected_chunk_keys(sample: EvalSample) -> set[tuple[str, int]]:
  expected = set(sample.expected_chunk_indices)
  expected.update(context.chunk_index for context in sample.expected_contexts)
  return {(sample.document_id, chunk_index) for chunk_index in expected}


def _expected_section_keys(sample: EvalSample) -> set[tuple[str, str]]:
  return {(sample.document_id, section) for section in sample.expected_sections}


def _result_chunk_keys(
  sample: EvalSample,
  result: EvalSampleResult,
  *,
  ranked: bool = False,
) -> list[tuple[str, int]]:
  if ranked and result.ranked_chunk_indices:
    document_ids = result.ranked_document_ids
    chunk_indices = result.ranked_chunk_indices
  else:
    document_ids = result.retrieved_document_ids
    chunk_indices = result.retrieved_chunk_indices
  return _result_keys(sample, result, document_ids, chunk_indices)


def _result_section_keys(
  sample: EvalSample,
  result: EvalSampleResult,
) -> list[tuple[str, str]]:
  return _result_keys(
    sample,
    result,
    result.retrieved_document_ids,
    result.retrieved_sections,
  )


def _result_keys(
  sample: EvalSample,
  result: EvalSampleResult,
  document_ids: list[str],
  values: list[T],
) -> list[tuple[str, T]]:
  if not values:
    return []
  if not document_ids:
    return [(sample.document_id, value) for value in values]
  return list(zip(document_ids, values, strict=True))


def _calculate_recall_at_k(
  sample: EvalSample,
  retrieved_chunk_keys: list[tuple[str, int]],
) -> float | None:
  expected = _expected_chunk_keys(sample)
  if not expected:
    return None
  hits = expected.intersection(retrieved_chunk_keys)
  return round(len(hits) / len(expected), 4)


def _calculate_ndcg_at_k(
  sample: EvalSample,
  retrieved_chunk_keys: list[tuple[str, int]],
) -> float | None:
  relevance_by_chunk = {
    (sample.document_id, context.chunk_index): context.relevance_grade
    for context in sample.expected_contexts
  }
  if not relevance_by_chunk:
    return None
  dcg = _dcg([relevance_by_chunk.get(chunk_key, 0) for chunk_key in retrieved_chunk_keys])
  ideal_grades = sorted(relevance_by_chunk.values(), reverse=True)[: len(retrieved_chunk_keys)]
  ideal_dcg = _dcg(ideal_grades)
  if ideal_dcg == 0:
    return None
  return round(dcg / ideal_dcg, 4)


def _dcg(grades: list[int]) -> float:
  return sum(
    grade / math.log2(rank + 1)
    for rank, grade in enumerate(grades, start=1)
  )


def _safe_recall(matches: int, total: int) -> float | None:
  if total == 0:
    return None
  return round(matches / total, 4)


def _calculate_mrr(
  retrieved_chunk_keys: list[tuple[str, int]],
  expected_chunk_keys: set[tuple[str, int]],
) -> float | None:
  if not expected_chunk_keys:
    return None
  for rank, chunk_key in enumerate(retrieved_chunk_keys, start=1):
    if chunk_key in expected_chunk_keys:
      return round(1 / rank, 4)
  return 0.0


def score_ragas_metrics(
  samples: list[EvalSample],
  results: list[EvalSampleResult],
  judge_model: str = "deepseek-v4-pro",
) -> list[EvalSampleResult]:
  """Score complete evaluation results with RAGAS."""
  completions = [result for result in results if result.status == "complete"]
  if not completions:
    return results

  samples_by_id = {sample.sample_id: sample for sample in samples}
  evaluator_llm = _build_evaluator_llm(judge_model)
  dataset = _build_evaluation_dataset(samples_by_id, completions)

  from ragas import evaluate

  ragas_result = evaluate(
    dataset=dataset,
    metrics=_build_ragas_metrics(evaluator_llm),
    llm=evaluator_llm,
    raise_exceptions=False,
  )
  rows = list(ragas_result.to_pandas().iterrows())
  for index, (_, row) in enumerate(rows):
    _assign_ragas_row(completions[index], row)
  return results


def _assign_ragas_row(result: EvalSampleResult, row: object) -> None:
  faithfulness = _safe_float(_row_get(row, "faithfulness"))
  answer_relevancy = _safe_float(_row_get(row, "answer_relevancy"))
  answer_correctness = _safe_float(_row_get(row, "answer_correctness"))
  factual_correctness = _safe_float(_row_get(row, "factual_correctness"))
  result.ragas_metrics = RagasMetricBundle(
    faithfulness=faithfulness,
    groundedness=faithfulness,
    context_recall=_safe_float(_row_get(row, "context_recall")),
    context_precision=_safe_float(_row_get(row, "context_precision")),
    answer_relevancy=answer_relevancy,
    answer_relevance=answer_relevancy,
    answer_correctness=answer_correctness,
    factual_correctness=factual_correctness,
  )


def _row_get(row: object, key: str) -> object:
  if isinstance(row, dict):
    return row.get(key)
  return row.get(key)


def _build_evaluation_dataset(
  samples_by_id: dict[str, EvalSample],
  results: list[EvalSampleResult],
) -> object:
  from ragas import EvaluationDataset

  return EvaluationDataset(samples=build_single_turn_samples(samples_by_id, results))


def _build_evaluator_llm(judge_model: str = "deepseek-v4-pro") -> object:
  from ragas.llms import LangchainLLMWrapper

  api_key = os.environ.get("DEEPSEEK_API_KEY") or settings.deepseek_api_key
  if not api_key:
    raise RuntimeError("RAGAS evaluation requires DEEPSEEK_API_KEY to be configured.")
  base_url = os.environ.get("DEEPSEEK_BASE_URL") or settings.deepseek_base_url
  model = os.environ.get("SCIPAL_EVAL_JUDGE_MODEL") or judge_model

  return LangchainLLMWrapper(
    ChatOpenAI(
      model=model,
      temperature=0,
      api_key=api_key,
      base_url=base_url,
    )
  )


def _build_ragas_metrics(evaluator_llm: object) -> list[object]:
  from ragas.metrics import AnswerRelevancy, ContextPrecision, ContextRecall, Faithfulness

  return [
    Faithfulness(llm=evaluator_llm),
    ContextRecall(llm=evaluator_llm),
    ContextPrecision(llm=evaluator_llm),
    AnswerRelevancy(llm=evaluator_llm, embeddings=_build_evaluator_embeddings()),
  ]


def _build_evaluator_embeddings() -> object:
  from langchain_huggingface import HuggingFaceEmbeddings

  return HuggingFaceEmbeddings(
    model_name=settings.embedding_model,
    model_kwargs={"device": settings.embedding_device},
    encode_kwargs={"normalize_embeddings": True},
  )


def _safe_float(value: object) -> float | None:
  if value is None:
    return None
  try:
    parsed = float(value)
  except (TypeError, ValueError):
    return None
  if math.isnan(parsed):
    return None
  return parsed
