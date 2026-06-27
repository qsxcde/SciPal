from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvalSample(BaseModel):
  model_config = ConfigDict(extra="forbid")

  sample_id: str
  session_id: str | None = None
  document_id: str
  question: str
  reference_answer: str
  expected_contexts: list["ExpectedContext"] = Field(default_factory=list)
  expected_sections: list[str] = Field(default_factory=list)
  expected_chunk_indices: list[int] = Field(default_factory=list)
  expected_evidence_text: list[str] = Field(default_factory=list)
  expected_citations: list["ExpectedCitation"] = Field(default_factory=list)
  answer_requirements: list[str] = Field(default_factory=list)
  negative_requirements: list[str] = Field(default_factory=list)
  question_type: str
  difficulty: str
  requires_abstention: bool = False
  review_status: Literal["draft", "approved"]
  generator: dict[str, object] | None = None
  notes: str = ""


class ExpectedContext(BaseModel):
  model_config = ConfigDict(extra="forbid")

  chunk_index: int
  section: str = ""
  text: str = ""
  relevance_grade: int = Field(default=1, ge=0, le=3)


class ExpectedCitation(BaseModel):
  model_config = ConfigDict(extra="forbid")

  section: str = ""
  chunk_index: int | None = None


class RetrievalConfig(BaseModel):
  model_config = ConfigDict(extra="forbid")

  name: str
  top_k: int
  max_expanded_chunks: int
  same_section_window: int
  adjacent_window: int
  include_linked_blocks: bool
  strategy: Literal["dense", "bm25", "hybrid"] = "dense"
  bm25_top_k: int = 5
  dense_top_k: int = 5
  seed_top_k: int = 5
  rrf_k: int = 60
  enable_reranker: bool = True
  rerank_top_k: int = 8

  @field_validator("top_k", "max_expanded_chunks")
  @classmethod
  def positive_int(cls, value: int) -> int:
    if value < 1:
      raise ValueError("value must be greater than 0")
    return value

  @field_validator("same_section_window", "adjacent_window")
  @classmethod
  def non_negative_int(cls, value: int) -> int:
    if value < 0:
      raise ValueError("value must be greater than or equal to 0")
    return value

  @field_validator("bm25_top_k", "dense_top_k", "seed_top_k", "rrf_k")
  @classmethod
  def non_negative_optional_int(cls, value: int) -> int:
    if value < 0:
      raise ValueError("value must be greater than or equal to 0")
    return value


class RetrievalMetricBundle(BaseModel):
  model_config = ConfigDict(extra="forbid")

  recall_at_k: float | None = None
  ndcg_at_k: float | None = None
  chunk_hit_rate: float | None = None
  chunk_recall: float | None = None
  section_hit_rate: float | None = None
  section_recall: float | None = None
  mrr: float | None = None
  retrieved_context_count: int = 0
  empty_retrieval: bool = False
  token_budget_proxy: int = 0


class RagasMetricBundle(BaseModel):
  model_config = ConfigDict(extra="forbid")

  faithfulness: float | None = None
  groundedness: float | None = None
  context_recall: float | None = None
  context_precision: float | None = None
  answer_relevancy: float | None = None
  answer_relevance: float | None = None
  answer_correctness: float | None = None
  factual_correctness: float | None = None


class JudgeMetricBundle(BaseModel):
  model_config = ConfigDict(extra="forbid")

  completeness: float | None = None
  citation_accuracy: float | None = None
  hallucination_rate: float | None = None
  task_success_rate: float | None = None
  end_to_end_answer_quality: float | None = None
  abstention_accuracy: float | None = None
  rationale: str = ""


class EvalSampleResult(BaseModel):
  model_config = ConfigDict(extra="forbid")

  sample_id: str
  config_name: str
  status: Literal["complete", "failed"]
  error_message: str = ""
  generated_answer: str = ""
  retrieved_contexts: list[str] = Field(default_factory=list)
  retrieved_document_ids: list[str] = Field(default_factory=list)
  retrieved_chunk_indices: list[int] = Field(default_factory=list)
  retrieved_sections: list[str] = Field(default_factory=list)
  ranked_document_ids: list[str] = Field(default_factory=list)
  ranked_chunk_indices: list[int] = Field(default_factory=list)
  ranked_sections: list[str] = Field(default_factory=list)
  retrieval_debug: dict[str, object] = Field(default_factory=dict)
  sources: list[dict[str, object]] = Field(default_factory=list)
  retrieval_metrics: RetrievalMetricBundle | None = None
  ragas_metrics: RagasMetricBundle | None = None
  judge_metrics: JudgeMetricBundle | None = None
  judge_warning: str = ""


class RunMetadata(BaseModel):
  model_config = ConfigDict(extra="forbid")

  run_id: str
  run_name: str
  dataset_path: str
  dataset_fingerprint: str
  baseline_eligible: bool
  config_set: str
  suite: Literal["retrieval", "generation", "e2e", "all"] = "retrieval"
  profile: Literal["regression", "judge", "full"] = "regression"
  scoring_mode: Literal["retrieval_only", "generation_only", "generation_with_ragas"]
  ragas_requested: bool
  judge_requested: bool = False
  judge_model: str = "deepseek-v4-pro"
  thresholds_path: str | None = None
  threshold_config: str | None = None
  fail_on_regression: bool = False
  warnings: list[str] = Field(default_factory=list)
  reproducibility_manifest: dict[str, object] = Field(default_factory=dict)


class RunSummary(BaseModel):
  model_config = ConfigDict(extra="forbid")

  run_metadata: RunMetadata
  overall_by_config: dict[str, dict[str, dict[str, float | int | None]]]
  grouped_by_config: dict[str, dict[str, dict[str, dict[str, float | int | None]]]]
  failure_summary: dict[str, int]
