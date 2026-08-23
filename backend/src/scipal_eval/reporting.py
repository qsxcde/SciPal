import json
from pathlib import Path

from scipal_eval.models import EvalSample, EvalSampleResult, RunMetadata


def write_run_outputs(
  output_dir: Path,
  *,
  run_metadata: RunMetadata,
  samples: list[EvalSample],
  results: list[EvalSampleResult],
) -> Path:
  """Write run artifacts for one evaluation execution."""
  run_dir = output_dir / run_metadata.run_id
  run_dir.mkdir(parents=True, exist_ok=True)
  (run_dir / "run_config.json").write_text(
    run_metadata.model_dump_json(indent=2),
    encoding="utf-8",
  )
  (run_dir / "dataset_fingerprint.txt").write_text(
    f"{run_metadata.dataset_fingerprint}\n",
    encoding="utf-8",
  )
  sample_rows = [sample.model_dump(mode="json") for sample in samples]
  result_rows = [result.model_dump(mode="json") for result in results]
  _write_jsonl(run_dir / "samples.jsonl", sample_rows)
  _write_jsonl(run_dir / "results.jsonl", result_rows)
  summary = _build_summary(run_metadata, samples, results)
  (run_dir / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2),
    encoding="utf-8",
  )
  (run_dir / "report.md").write_text(_render_report(summary), encoding="utf-8")
  (run_dir / "comparison.md").write_text(_render_comparison(summary), encoding="utf-8")
  (run_dir / "failures.md").write_text(_render_failures(results), encoding="utf-8")
  return run_dir


def save_baseline(run_dir: Path, output_path: Path) -> None:
  """Persist a run summary as the baseline artifact for later comparisons."""
  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(
    (run_dir / "summary.json").read_text(encoding="utf-8"),
    encoding="utf-8",
  )


def compare_baseline(baseline_path: Path, current_summary_path: Path) -> str:
  """Render a markdown comparison between a baseline summary and the current run summary."""
  baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
  current = json.loads(current_summary_path.read_text(encoding="utf-8"))
  baseline_metadata = baseline.get("run_metadata", {})
  current_metadata = current.get("run_metadata", {})
  if baseline_metadata.get("dataset_fingerprint") != current_metadata.get("dataset_fingerprint"):
    return "# Baseline Comparison\n\nComparable: false\n\nReason: dataset fingerprint mismatch\n"
  if not _manifests_match(
    baseline_metadata.get("reproducibility_manifest", {}),
    current_metadata.get("reproducibility_manifest", {}),
  ):
    return "# Baseline Comparison\n\nComparable: false\n\nReason: reproducibility manifest mismatch\n"

  lines = ["# Baseline Comparison", "", "Comparable: true", ""]
  current_overall = current.get("overall_by_config", {})
  baseline_overall = baseline.get("overall_by_config", {})
  for config_name, current_metrics in current_overall.items():
    if not isinstance(current_metrics, dict):
      continue
    baseline_metrics = baseline_overall.get(config_name, {})
    if not isinstance(baseline_metrics, dict):
      baseline_metrics = {}
    lines.append(f"## {config_name}")
    lines.append("")
    for group_name in ("ragas", "retrieval"):
      lines.append(f"### {group_name}")
      current_group = current_metrics.get(group_name, {})
      baseline_group = baseline_metrics.get(group_name, {})
      if not isinstance(current_group, dict):
        current_group = {}
      if not isinstance(baseline_group, dict):
        baseline_group = {}
      for metric_name, current_value in current_group.items():
        old_value = baseline_group.get(metric_name)
        if isinstance(current_value, (int, float)) and isinstance(old_value, (int, float)):
          delta = round(current_value - old_value, 4)
          lines.append(f"- `{metric_name}`: {old_value} -> {current_value} ({delta:+.4f})")
      lines.append("")
  return "\n".join(lines).rstrip() + "\n"


def _manifests_match(baseline: object, current: object) -> bool:
  """Compare JSON-compatible manifests independent of dictionary insertion order."""
  try:
    return json.dumps(baseline, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == json.dumps(
      current,
      ensure_ascii=False,
      sort_keys=True,
      separators=(",", ":"),
    )
  except (TypeError, ValueError):
    return False


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
  path.write_text(
    "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
    encoding="utf-8",
  )


def _build_summary(
  run_metadata: RunMetadata,
  samples: list[EvalSample],
  results: list[EvalSampleResult],
) -> dict[str, object]:
  failed_metric_count = 0
  if run_metadata.ragas_requested:
    failed_metric_count = sum(
      1
      for result in results
      if result.status == "complete" and result.ragas_metrics is None
    )

  return {
    "run_metadata": run_metadata.model_dump(mode="json"),
    "suite_metrics": _suite_metrics(results, threshold_config=run_metadata.threshold_config),
    "overall_by_config": _overall_by_config(results),
    "grouped_by_config": _grouped_by_config(samples, results),
    "failure_summary": {
      "failed_result_count": sum(1 for result in results if result.status == "failed"),
      "failed_metric_count": failed_metric_count,
    },
  }


def _suite_metrics(
  results: list[EvalSampleResult],
  *,
  threshold_config: str | None = None,
) -> dict[str, dict[str, float | int | None]]:
  scoped_results = _select_suite_metric_results(results, threshold_config=threshold_config)
  return {
    "retrieval": {
      "recall_at_k": _mean_metric(scoped_results, "retrieval_metrics", "recall_at_k"),
      "ndcg_at_k": _mean_metric(scoped_results, "retrieval_metrics", "ndcg_at_k"),
      "context_recall": _mean_metric(scoped_results, "ragas_metrics", "context_recall"),
    },
    "generation": {
      "faithfulness": _mean_metric(scoped_results, "ragas_metrics", "faithfulness"),
      "groundedness": _mean_metric(scoped_results, "ragas_metrics", "groundedness"),
      "answer_relevance": _mean_metric(scoped_results, "ragas_metrics", "answer_relevance"),
      "completeness": _mean_metric(scoped_results, "judge_metrics", "completeness"),
      "citation_accuracy": _mean_metric(scoped_results, "judge_metrics", "citation_accuracy"),
      "hallucination_rate": _mean_metric(scoped_results, "judge_metrics", "hallucination_rate"),
    },
    "e2e": {
      "task_success_rate": _mean_metric(scoped_results, "judge_metrics", "task_success_rate"),
      "end_to_end_answer_quality": _mean_metric(scoped_results, "judge_metrics", "end_to_end_answer_quality"),
      "faithfulness": _mean_metric(scoped_results, "ragas_metrics", "faithfulness"),
      "groundedness": _mean_metric(scoped_results, "ragas_metrics", "groundedness"),
      "citation_accuracy": _mean_metric(scoped_results, "judge_metrics", "citation_accuracy"),
      "abstention_accuracy": _mean_metric(scoped_results, "judge_metrics", "abstention_accuracy"),
    },
  }


def _select_suite_metric_results(
  results: list[EvalSampleResult],
  *,
  threshold_config: str | None,
) -> list[EvalSampleResult]:
  if threshold_config is None:
    return results
  return [result for result in results if result.config_name == threshold_config]


def _mean_metric(
  results: list[EvalSampleResult],
  bundle_name: str,
  metric_name: str,
) -> float | int | None:
  values: list[float] = []
  for result in results:
    if result.status != "complete":
      continue
    bundle = getattr(result, bundle_name)
    if bundle is None:
      continue
    value = getattr(bundle, metric_name)
    if isinstance(value, bool):
      values.append(1.0 if value else 0.0)
    elif isinstance(value, (int, float)):
      values.append(float(value))
  if not values:
    return None
  return round(sum(values) / len(values), 4)


def _overall_by_config(
  results: list[EvalSampleResult],
) -> dict[str, dict[str, dict[str, float | int | None]]]:
  grouped: dict[str, list[EvalSampleResult]] = {}
  for result in results:
    grouped.setdefault(result.config_name, []).append(result)
  return {
    config_name: _aggregate_results(config_results)
    for config_name, config_results in grouped.items()
  }


def _grouped_by_config(
  samples: list[EvalSample],
  results: list[EvalSampleResult],
) -> dict[str, dict[str, dict[str, dict[str, float | int | None]]]]:
  samples_by_id = {sample.sample_id: sample for sample in samples}
  grouped: dict[str, dict[str, dict[str, list[EvalSampleResult]]]] = {}
  for result in results:
    sample = samples_by_id[result.sample_id]
    config_groups = grouped.setdefault(
      result.config_name,
      {
        "by_question_type": {},
        "by_difficulty": {},
        "by_document": {},
        "by_language_route": {},
      },
    )
    _append_group(config_groups["by_question_type"], sample.question_type, result)
    _append_group(config_groups["by_difficulty"], sample.difficulty, result)
    _append_group(config_groups["by_document"], sample.document_id, result)
    _append_group(config_groups["by_language_route"], _language_route(result), result)

  return {
    config_name: {
      group_name: {
        group_key: _aggregate_results(group_results)
        for group_key, group_results in group_values.items()
      }
      for group_name, group_values in config_groups.items()
    }
    for config_name, config_groups in grouped.items()
  }


def _append_group(
  groups: dict[str, list[EvalSampleResult]],
  key: str,
  result: EvalSampleResult,
) -> None:
  groups.setdefault(key, []).append(result)


def _language_route(result: EvalSampleResult) -> str:
  route = result.retrieval_debug.get("route")
  if not isinstance(route, dict):
    return "unknown"
  used_query_pack = route.get("used_query_pack")
  if used_query_pack is True:
    return "cross_language"
  if used_query_pack is False:
    return "same_language"
  return "unknown"


def _aggregate_results(
  results: list[EvalSampleResult],
) -> dict[str, dict[str, float | int | None]]:
  ragas_rows = [
    result.ragas_metrics.model_dump(mode="json")
    for result in results
    if result.status == "complete" and result.ragas_metrics is not None
  ]
  retrieval_rows = [
    result.retrieval_metrics.model_dump(mode="json")
    for result in results
    if result.status == "complete" and result.retrieval_metrics is not None
  ]
  total_sample_count = len(results)
  scored_sample_count = len(retrieval_rows)
  failed_sample_count = sum(result.status == "failed" for result in results)
  retrieval = _average_metric_dict(retrieval_rows)
  retrieval.update(
    {
      "total_sample_count": total_sample_count,
      "scored_sample_count": scored_sample_count,
      "failed_sample_count": failed_sample_count,
      "execution_failure_rate": round(failed_sample_count / total_sample_count, 4)
      if total_sample_count
      else 0.0,
    }
  )
  return {
    "ragas": _average_metric_dict(ragas_rows),
    "retrieval": retrieval,
  }


def _average_metric_dict(rows: list[dict[str, object]]) -> dict[str, float | int | None]:
  totals: dict[str, float] = {}
  counts: dict[str, int] = {}
  for row in rows:
    for name, value in row.items():
      metric_name = "empty_retrieval_rate" if name == "empty_retrieval" else name
      if isinstance(value, bool):
        numeric_value = 1.0 if value else 0.0
      elif isinstance(value, (int, float)):
        numeric_value = float(value)
      else:
        continue
      totals[metric_name] = totals.get(metric_name, 0.0) + numeric_value
      counts[metric_name] = counts.get(metric_name, 0) + 1
  return {
    name: round(totals[name] / counts[name], 4)
    for name in totals
  }


def _render_report(summary: dict[str, object]) -> str:
  lines = ["# RAGAS Evaluation Report", ""]
  overall = summary.get("overall_by_config", {})
  if not isinstance(overall, dict):
    return "\n".join(lines).rstrip() + "\n"

  for config_name, metrics in overall.items():
    lines.append(f"## {config_name}")
    lines.append("")
    lines.append(json.dumps(metrics, ensure_ascii=False, indent=2))
    lines.append("")
  return "\n".join(lines).rstrip() + "\n"


def _render_comparison(summary: dict[str, object]) -> str:
  overall = summary.get("overall_by_config", {})
  if not isinstance(overall, dict):
    return "# Config Comparison\n\nNo metrics available.\n"

  baseline_name = _select_comparison_baseline(overall)
  baseline = overall.get(baseline_name)
  if not isinstance(baseline, dict):
    return "# Config Comparison\n\nNo comparable baseline config found.\n"

  lines = ["# Config Comparison", ""]
  for config_name, metrics in overall.items():
    if config_name == baseline_name or not isinstance(metrics, dict):
      continue
    lines.append(f"## {config_name} vs {baseline_name}")
    lines.append("")
    for group_name in ("ragas", "retrieval"):
      baseline_group = baseline.get(group_name, {})
      current_group = metrics.get(group_name, {})
      if not isinstance(baseline_group, dict) or not isinstance(current_group, dict):
        continue
      lines.append(f"### {group_name}")
      for metric_name, current_value in current_group.items():
        old_value = baseline_group.get(metric_name)
        if isinstance(current_value, (int, float)) and isinstance(old_value, (int, float)):
          delta = round(current_value - old_value, 4)
          lines.append(f"- `{metric_name}`: {old_value} -> {current_value} ({delta:+.4f})")
      lines.append("")
  return "\n".join(lines).rstrip() + "\n"


def _select_comparison_baseline(
  overall: dict[str, object],
) -> str:
  for candidate in ("top5_default", "dense_baseline"):
    if candidate in overall:
      return candidate
  return next(iter(overall), "")


def _render_failures(results: list[EvalSampleResult]) -> str:
  failures = [
    result
    for result in results
    if result.status == "failed" or result.judge_warning
  ]
  if not failures:
    return "# Failures\n\nNo failures.\n"
  lines = ["# Failures", ""]
  for result in failures:
    lines.append(
      "- {} / {}: {}".format(
        result.sample_id,
        result.config_name,
        result.error_message or result.judge_warning,
      )
    )
  return "\n".join(lines).rstrip() + "\n"
