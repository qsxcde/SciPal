from backend.evals.models import EvalSample, EvalSampleResult


def build_single_turn_samples(
  samples_by_id: dict[str, EvalSample],
  results: list[EvalSampleResult],
) -> list[object]:
  """Build RAGAS SingleTurnSample objects for complete SciPal results."""
  from ragas.dataset_schema import SingleTurnSample

  ragas_samples: list[object] = []
  for result in results:
    if result.status != "complete":
      continue
    sample = samples_by_id[result.sample_id]
    ragas_samples.append(
      SingleTurnSample(
        user_input=sample.question,
        response=result.generated_answer,
        retrieved_contexts=result.retrieved_contexts,
        reference=sample.reference_answer,
      )
    )
  return ragas_samples
