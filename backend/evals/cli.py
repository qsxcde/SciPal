import argparse
import asyncio
import json
from collections.abc import Coroutine
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

_T = TypeVar("_T")

from backend.evals.configs import get_config_set
from backend.evals.dataset import dataset_fingerprint, load_dataset
from backend.evals.metrics import score_ragas_metrics
from backend.evals.models import EvalSample, RetrievalConfig, RunMetadata
from backend.evals.pipeline import run_pipeline
from backend.evals.reporting import compare_baseline, save_baseline, write_run_outputs

if TYPE_CHECKING:
  from backend.rag.pipeline.online_pipeline import ChatEvaluationResult


def build_parser() -> argparse.ArgumentParser:
  """Build the command-line parser for ragas evaluation workflows."""
  parser = argparse.ArgumentParser(prog="ragas-evals")
  subparsers = parser.add_subparsers(dest="command", required=True)

  run_parser = subparsers.add_parser("run")
  run_parser.add_argument("--dataset", required=True, type=Path)
  run_parser.add_argument("--session-id", required=False)
  run_parser.add_argument("--config-set", required=True)
  run_parser.add_argument("--output-dir", required=True, type=Path)
  run_parser.add_argument("--run-name", required=True)
  run_parser.add_argument("--allow-draft", action="store_true")
  run_parser.add_argument("--with-generation", action="store_true")
  run_parser.add_argument("--with-ragas", action="store_true")
  run_parser.add_argument("--suite", choices=["retrieval", "generation", "e2e", "all"], default="retrieval")
  run_parser.add_argument("--profile", choices=["regression", "judge", "full"], default="regression")
  run_parser.add_argument("--with-judge", action="store_true")
  run_parser.add_argument("--judge-model", default="deepseek-v4-pro")
  run_parser.add_argument("--fail-on-regression", action="store_true")
  run_parser.add_argument("--thresholds", type=Path)
  run_parser.add_argument("--threshold-config")

  compare_parser = subparsers.add_parser("compare")
  compare_parser.add_argument("--baseline", required=True, type=Path)
  compare_parser.add_argument("--current", required=True, type=Path)

  baseline_parser = subparsers.add_parser("baseline-save")
  baseline_parser.add_argument("--run-dir", required=True, type=Path)
  baseline_parser.add_argument("--output", required=True, type=Path)

  draft_parser = subparsers.add_parser("generate-draft")
  draft_parser.add_argument("--session-id", required=True)
  draft_parser.add_argument("--output", required=True, type=Path)
  draft_parser.add_argument("--max-samples", type=int, default=30)
  draft_parser.add_argument("--question-types")
  draft_parser.add_argument("--generator-model", default="deepseek-v4-pro")
  draft_parser.add_argument("--no-llm", action="store_true")

  return parser


def main(argv: list[str] | None = None) -> None:
  """Dispatch CLI subcommands."""
  parser = build_parser()
  args = parser.parse_args(argv)
  if args.command == "run" and args.with_ragas and not args.with_generation:
    parser.error("--with-ragas requires --with-generation")
  if args.command == "run":
    _run_command(args)
  elif args.command == "compare":
    print(compare_baseline(args.baseline, args.current))
  elif args.command == "baseline-save":
    save_baseline(args.run_dir, args.output)
  elif args.command == "generate-draft":
    from backend.evals.draft_generator import generate_draft_dataset
    from backend.evals.draft_generator import parse_question_types

    count = generate_draft_dataset(
      args.session_id,
      args.output,
      max_samples=args.max_samples,
      question_types=parse_question_types(args.question_types),
      use_llm=not args.no_llm,
      generator_model=args.generator_model,
    )
    print(f"Generated {count} draft samples at {args.output}")


def _run_command(args: argparse.Namespace) -> None:
  """Run one configured evaluation sweep and write artifacts."""
  samples = load_dataset(args.dataset, allow_draft=args.allow_draft)
  configs = get_config_set(args.config_set)
  threshold_config = _resolve_threshold_config(
    configs,
    requested_threshold_config=args.threshold_config,
    fail_on_regression=args.fail_on_regression,
  )
  fingerprint = dataset_fingerprint(samples)
  evaluator = _evaluate_with_scipal if args.with_generation else _evaluate_retrieval_only
  ragas_requested = args.with_ragas or args.profile == "full"
  judge_requested = args.with_judge or args.profile in {"judge", "full"}
  reproducibility_manifest = _build_reproducibility_manifest(
    samples,
    default_session_id=args.session_id,
  )
  results = run_pipeline(
    samples,
    configs,
    default_session_id=args.session_id,
    evaluator=evaluator,
  )
  scored_results = score_ragas_metrics(samples, results) if ragas_requested else results
  scored_results = (
    score_judge_metrics(samples, scored_results, judge_model=args.judge_model)
    if judge_requested
    else scored_results
  )
  metadata = RunMetadata(
    run_id=_build_run_id(args.run_name),
    run_name=args.run_name,
    dataset_path=str(args.dataset),
    dataset_fingerprint=fingerprint,
    baseline_eligible=not args.allow_draft,
    config_set=args.config_set,
    suite=args.suite,
    profile=args.profile,
    scoring_mode=_build_scoring_mode(
      with_generation=args.with_generation,
      with_ragas=ragas_requested,
    ),
    ragas_requested=ragas_requested,
    judge_requested=judge_requested,
    judge_model=args.judge_model,
    thresholds_path=str(args.thresholds) if args.thresholds is not None else None,
    threshold_config=threshold_config,
    fail_on_regression=args.fail_on_regression,
    warnings=_build_run_warnings(args.with_generation, ragas_requested),
    reproducibility_manifest=reproducibility_manifest,
  )
  run_dir = write_run_outputs(
    args.output_dir,
    run_metadata=metadata,
    samples=samples,
    results=scored_results,
  )
  if args.fail_on_regression:
    from backend.evals.thresholds import evaluate_thresholds
    from backend.evals.thresholds import load_thresholds

    threshold_path = args.thresholds or Path("backend/configs/eval_thresholds.yaml")
    summary_path = run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    violations = evaluate_thresholds(summary, load_thresholds(threshold_path))
    if violations:
      message = "\n".join(
        f"{violation.metric_path}: actual={violation.actual} violates {violation.rule}"
        for violation in violations
      )
      raise SystemExit(f"Evaluation thresholds failed:\n{message}")
  print(f"Run complete: {run_dir}")


def _resolve_threshold_config(
  configs: list[RetrievalConfig],
  *,
  requested_threshold_config: str | None,
  fail_on_regression: bool,
) -> str | None:
  config_names = [config.name for config in configs]
  if requested_threshold_config is not None:
    if requested_threshold_config not in config_names:
      raise SystemExit(
        f"Unknown --threshold-config '{requested_threshold_config}'. Available configs: {', '.join(config_names)}"
      )
    return requested_threshold_config
  if len(config_names) == 1:
    return config_names[0]
  if fail_on_regression:
    raise SystemExit(
      "--fail-on-regression with multiple configs requires --threshold-config to select one config for threshold checks"
    )
  return None


def score_judge_metrics(
  samples: list[object],
  results: list[object],
  *,
  judge_model: str,
) -> list[object]:
  from backend.evals.judge import score_judge_metrics as score_with_judge

  return score_with_judge(samples, results, judge_model=judge_model)


def _evaluate_with_scipal(
  session_id: str,
  question: str,
  config: RetrievalConfig,
) -> "ChatEvaluationResult":
  """Evaluate one question against a live SciPal session with retrieval overrides."""
  from backend.rag.pipeline.online_pipeline import RetrievalOptions
  from backend.app.services.chat_service import evaluate_session_chat

  retrieval_options = RetrievalOptions(
    strategy=config.strategy,
    max_expanded_chunks=config.max_expanded_chunks,
    same_section_window=config.same_section_window,
    adjacent_window=config.adjacent_window,
    include_linked_blocks=config.include_linked_blocks,
    bm25_top_k=config.bm25_top_k,
    dense_top_k=config.dense_top_k,
    seed_top_k=config.seed_top_k,
    rrf_k=config.rrf_k,
  )
  return _run_async(evaluate_session_chat(
    session_id=session_id,
    content=question,
    top_k=config.top_k,
    retrieval_options=retrieval_options,
  ))


def _run_async(coro: "Coroutine[None, None, _T]") -> _T:
    """Safely run a coroutine from CLI context; raises if called within an event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        "This async CLI helper is called from within a running event loop. "
        "Invoke the coroutine directly instead."
    )


def _evaluate_retrieval_only(
  session_id: str,
  question: str,
  config: RetrievalConfig,
) -> "ChatEvaluationResult":
  """Evaluate one question against a SciPal session without live generation."""
  from backend.rag.pipeline.online_pipeline import RetrievalOptions
  from backend.app.services.chat_service import evaluate_session_retrieval

  retrieval_options = RetrievalOptions(
    strategy=config.strategy,
    max_expanded_chunks=config.max_expanded_chunks,
    same_section_window=config.same_section_window,
    adjacent_window=config.adjacent_window,
    include_linked_blocks=config.include_linked_blocks,
    bm25_top_k=config.bm25_top_k,
    dense_top_k=config.dense_top_k,
    seed_top_k=config.seed_top_k,
    rrf_k=config.rrf_k,
  )
  return _run_async(evaluate_session_retrieval(
    session_id=session_id,
    content=question,
    top_k=config.top_k,
    retrieval_options=retrieval_options,
  ))


def _build_run_warnings(with_generation: bool, with_ragas: bool) -> list[str]:
  warnings: list[str] = []
  if not with_generation:
    warnings.append("Generation skipped; this run contains retrieval-only metrics.")
  if with_generation and not with_ragas:
    warnings.append("RAGAS scoring skipped; this run contains retrieval metrics only.")
  return warnings


def _build_scoring_mode(*, with_generation: bool, with_ragas: bool) -> str:
  if not with_generation:
    return "retrieval_only"
  if with_ragas:
    return "generation_with_ragas"
  return "generation_only"


def _build_reproducibility_manifest(
  samples: list[EvalSample],
  *,
  default_session_id: str | None,
) -> dict[str, object]:
  """Capture the ready index snapshot used by each resolved evaluation session."""
  from backend.domain.config import settings
  from backend.storage.sqlite.index_snapshots import get_active_ready_snapshot
  from backend.storage.sqlite.sessions import get_session

  session_ids = sorted(
    {
      session_id
      for sample in samples
      if (session_id := sample.session_id or default_session_id) is not None
    }
  )
  sessions: list[dict[str, object]] = []
  for session_id in session_ids:
    try:
      session = get_session(session_id)
    except Exception:
      sessions.append(_unavailable_manifest_session(session_id, "unavailable"))
      continue
    if session is None:
      sessions.append(_unavailable_manifest_session(session_id, "missing"))
      continue
    if session.get("is_archived"):
      sessions.append(_unavailable_manifest_session(session_id, "unavailable"))
      continue
    try:
      snapshot = get_active_ready_snapshot(session_id)
    except Exception:
      sessions.append(_unavailable_manifest_session(session_id, "unavailable"))
      continue
    if snapshot is None:
      sessions.append(_unavailable_manifest_session(session_id, "no_ready_snapshot"))
      continue
    document_ids = snapshot.get("document_ids", [])
    sessions.append(
      {
        "session_id": session_id,
        "availability": "ready",
        "active_snapshot_id": snapshot.get("id"),
        "snapshot_updated_at": snapshot.get("updated_at"),
        "document_ids": sorted(str(document_id) for document_id in document_ids),
      }
    )
  return {
    "sessions": sessions,
    "embedding_model": settings.embedding_model,
  }


def _unavailable_manifest_session(session_id: str, availability: str) -> dict[str, object]:
  return {
    "session_id": session_id,
    "availability": availability,
    "active_snapshot_id": None,
    "snapshot_updated_at": None,
    "document_ids": [],
  }


def _build_run_id(run_name: str) -> str:
  """Build a filesystem-safe run id with a UTC timestamp suffix."""
  timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
  safe_name = "".join(char if char.isalnum() or char in "-_" else "-" for char in run_name).strip("-")
  return f"{safe_name}-{timestamp}"


if __name__ == "__main__":
  main()
