import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from scipal_eval.models import EvalSample


def load_dataset(path: Path, *, allow_draft: bool = False) -> list[EvalSample]:
  """Load and validate a JSONL evaluation dataset."""
  samples: list[EvalSample] = []
  with path.open("r", encoding="utf-8") as handle:
    for line_number, line in enumerate(handle, start=1):
      if not line.strip():
        continue
      try:
        sample = EvalSample.model_validate(json.loads(line))
      except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"Invalid dataset row at line {line_number}: {exc}") from exc
      if sample.review_status == "draft" and not allow_draft:
        raise ValueError(
          f"Dataset contains draft sample {sample.sample_id}; pass --allow-draft for exploratory runs"
        )
      if sample.requires_abstention and (sample.expected_sections or sample.expected_chunk_indices):
        raise ValueError(
          f"Sample {sample.sample_id} requires_abstention=True but also has expected_sections or expected_chunk_indices"
        )
      if (
        not sample.requires_abstention
        and not sample.expected_sections
        and not sample.expected_chunk_indices
      ):
        raise ValueError(
          f"Sample {sample.sample_id} must include expected_sections or expected_chunk_indices"
        )
      samples.append(sample)
  if not samples:
    raise ValueError(f"Dataset is empty: {path}")
  _ensure_unique_sample_ids(samples)
  return samples


def dataset_fingerprint(samples: list[EvalSample]) -> str:
  """Return a stable fingerprint for a dataset independent of JSONL row order."""
  canonical_rows = [sample.model_dump(mode="json") for sample in sorted(samples, key=lambda item: item.sample_id)]
  payload = json.dumps(canonical_rows, ensure_ascii=False, sort_keys=True)
  return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ensure_unique_sample_ids(samples: list[EvalSample]) -> None:
  seen: set[str] = set()
  for sample in samples:
    if sample.sample_id in seen:
      raise ValueError(f"Duplicate sample_id: {sample.sample_id}")
    seen.add(sample.sample_id)
