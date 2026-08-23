from collections.abc import Callable
from typing import Protocol

from backend.evals.metrics import calculate_retrieval_metrics
from backend.evals.models import EvalSample, EvalSampleResult, RetrievalConfig


class ChunkMetadataLike(Protocol):
  paper_id: str
  chunk_index: int
  section: str


class RetrievedChunkLike(Protocol):
  text: str
  metadata: ChunkMetadataLike


class SourceLike(Protocol):
  def model_dump(self) -> dict[str, object]:
    ...


class EvaluationResultLike(Protocol):
  answer: str
  retrieved_chunks: list[RetrievedChunkLike]
  sources: list[SourceLike]
  generation_mode: str
  ranked_chunks: list[RetrievedChunkLike]
  retrieval_debug: dict[str, object]


Evaluator = Callable[[str, str, RetrievalConfig], EvaluationResultLike]


def run_pipeline(
  samples: list[EvalSample],
  configs: list[RetrievalConfig],
  *,
  default_session_id: str | None = None,
  evaluator: Evaluator,
) -> list[EvalSampleResult]:
  """Run every sample against every retrieval configuration."""
  results: list[EvalSampleResult] = []
  for sample in samples:
    session_id = sample.session_id or default_session_id
    if session_id is None:
      raise ValueError(f"Sample {sample.sample_id} has no session_id and no default session was provided")
    for config in configs:
      result = _run_single(sample, session_id, config, evaluator)
      if result.status == "complete":
        result.retrieval_metrics = calculate_retrieval_metrics(sample, result)
      results.append(result)
  return results


def _run_single(
  sample: EvalSample,
  session_id: str,
  config: RetrievalConfig,
  evaluator: Evaluator,
) -> EvalSampleResult:
  try:
    evaluation = evaluator(session_id, sample.question, config)
  except Exception as exc:
    return EvalSampleResult(
      sample_id=sample.sample_id,
      config_name=config.name,
      status="failed",
      error_message=str(exc),
    )

  retrieved_contexts = [chunk.text for chunk in evaluation.retrieved_chunks]
  retrieved_document_ids = [chunk.metadata.paper_id for chunk in evaluation.retrieved_chunks]
  retrieved_chunk_indices = [chunk.metadata.chunk_index for chunk in evaluation.retrieved_chunks]
  retrieved_sections = [chunk.metadata.section for chunk in evaluation.retrieved_chunks]
  ranked_chunks = getattr(evaluation, "ranked_chunks", evaluation.retrieved_chunks)
  ranked_document_ids = [chunk.metadata.paper_id for chunk in ranked_chunks]
  ranked_chunk_indices = [chunk.metadata.chunk_index for chunk in ranked_chunks]
  ranked_sections = [chunk.metadata.section for chunk in ranked_chunks]
  sources = [source.model_dump() for source in evaluation.sources]
  retrieval_debug = getattr(evaluation, "retrieval_debug", {})
  is_retrieval_only = evaluation.generation_mode == "skipped"
  has_required_output = bool(retrieved_contexts) and (is_retrieval_only or bool(evaluation.answer))
  status = "complete" if has_required_output else "failed"
  error_message = "" if status == "complete" else "empty retrieval or answer"

  return EvalSampleResult(
    sample_id=sample.sample_id,
    config_name=config.name,
    status=status,
    error_message=error_message,
    generated_answer=evaluation.answer,
    retrieved_contexts=retrieved_contexts,
    retrieved_document_ids=retrieved_document_ids,
    retrieved_chunk_indices=retrieved_chunk_indices,
    retrieved_sections=retrieved_sections,
    ranked_document_ids=ranked_document_ids,
    ranked_chunk_indices=ranked_chunk_indices,
    ranked_sections=ranked_sections,
    retrieval_debug=retrieval_debug,
    sources=sources,
  )
