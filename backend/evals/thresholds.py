from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class ThresholdViolation(BaseModel):
  metric_path: str
  actual: float | None
  rule: str


def load_thresholds(path: Path) -> dict[str, Any]:
  return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def evaluate_thresholds(
  summary: dict[str, object],
  thresholds: dict[str, object],
) -> list[ThresholdViolation]:
  suite_metrics = summary.get("suite_metrics", {})
  if not isinstance(suite_metrics, dict):
    return []
  violations: list[ThresholdViolation] = []
  for suite_name, metric_rules in thresholds.items():
    if not isinstance(metric_rules, dict):
      continue
    suite_values = suite_metrics.get(suite_name, {})
    if not isinstance(suite_values, dict):
      suite_values = {}
    for metric_name, rule in metric_rules.items():
      if not isinstance(rule, dict):
        continue
      actual = _as_float(suite_values.get(metric_name))
      metric_path = f"{suite_name}.{metric_name}"
      if "min" in rule and actual is not None and actual < float(rule["min"]):
        violations.append(
          ThresholdViolation(
            metric_path=metric_path,
            actual=actual,
            rule=f"min {rule['min']}",
          )
        )
      if "max" in rule and actual is not None and actual > float(rule["max"]):
        violations.append(
          ThresholdViolation(
            metric_path=metric_path,
            actual=actual,
            rule=f"max {rule['max']}",
          )
        )
  return violations


def _as_float(value: object) -> float | None:
  if value is None:
    return None
  try:
    return float(value)
  except (TypeError, ValueError):
    return None
