# NEXUS ACADEMY Offline Evaluation

- Dataset version: `1.0.0`
- Mode: `offline_deterministic_synthetic_fixtures`
- Checks passed: 19/21

## Sample Counts

| Sample | Count |
|---|---:|
| documents | 5 |
| source records | 8 |
| qa cases | 6 |
| answerable qa cases | 4 |
| unanswerable qa cases | 2 |
| quiz checks | 2 |
| simulated learners | 2 |

All ratios include explicit numerators and denominators. A failed check records current behavior; it is not concealed by the runner.

## Grounded Qa

| Metric | Value | Numerator / denominator |
|---|---:|---:|
| answerable coverage | 1.0000 | 4 / 4 |
| citation source record accuracy | 1.0000 | 4 / 4 |
| citation location accuracy | 1.0000 | 4 / 4 |
| citation correctness | 1.0000 | 4 / 4 |
| evidence support rate | 1.0000 | 4 / 4 |
| appropriate abstention rate | 0.5000 | 1 / 2 |
| unsupported answer rate | 0.5000 | 1 / 2 |

## Quiz

| Metric | Value | Numerator / denominator |
|---|---:|---:|
| generated questions vs requested | 0.3846 | 5 / 13 |
| valid source reference rate | 1.0000 | 5 / 5 |
| answer key consistency rate | 1.0000 | 5 / 5 |
| duplicate question rate | 0.0000 | 0 / 5 |
| url or heading option rate | 0.0000 | 0 / 20 |
| quality rule satisfaction rate | 1.0000 | 5 / 5 |
| blocked candidate rejection rate | 1.0000 | 5 / 5 |
| insufficient content report rate | 1.0000 | 1 / 1 |

## Personalization

| Metric | Value | Numerator / denominator |
|---|---:|---:|
| weak concept mastery | 1.0000 | 1 / 1 |
| strong concept mastery | 1.0000 | 1 / 1 |
| weak concept prioritized | 1.0000 | 1 / 1 |
| unseen concept selected | 1.0000 | 1 / 1 |
| strong concept not overprioritized | 1.0000 | 1 / 1 |
| retry not double counted | 1.0000 | 1 / 1 |
| adaptive exact repeat avoidance | 1.0000 | 8 / 8 |
| learner isolation | 1.0000 | 1 / 1 |
| document isolation | 1.0000 | 5 / 5 |

## Checks

| Check | Result | Observed | Expected |
|---|---|---:|---|
| answerable_question_coverage | PASS | 1.0 | 1.0 |
| citation_record_accuracy | PASS | 1.0 | 1.0 |
| citation_location_accuracy | PASS | 1.0 | 1.0 |
| fixture_evidence_support | PASS | 1.0 | 1.0 |
| unanswerable_abstention | FAIL | 0.5 | 1.0 |
| quiz_source_references | PASS | 1.0 | 1.0 |
| quiz_answer_keys | PASS | 1.0 | 1.0 |
| quiz_duplicates | PASS | 0.0 | 0.0 |
| quiz_url_heading_options | PASS | 0.0 | 0.0 |
| quiz_quality_rules | PASS | 1.0 | 1.0 |
| insufficient_source_reported | PASS | 1.0 | 1.0 |
| weak_concept_mastery | PASS | 1.0 | 1.0 |
| strong_concept_mastery | PASS | 1.0 | 1.0 |
| weak_concept_prioritized | PASS | 1.0 | 1.0 |
| unseen_concept_selected | PASS | 1.0 | 1.0 |
| strong_concept_not_overprioritized | PASS | 1.0 | 1.0 |
| retry_not_double_counted | PASS | 1.0 | 1.0 |
| adaptive_exact_repeat_avoidance | PASS | 1.0 | 1.0 |
| learner_isolation | PASS | 1.0 | 1.0 |
| document_isolation | PASS | 1.0 | 1.0 |
| no_unsupported_answers | FAIL | 0.5 | 0.0 |

## Limitations

- Evidence support is checked by manually specified fixture terms, not semantic entailment.
- Citation correctness and answer support are measured separately.
- Keyword overlap can produce unsupported answers for misleading queries; this is measured as a failure, not hidden.
- Quiz checks validate deterministic template rules, not pedagogical quality or distractor usefulness.
- Learner results are deterministic policy checks over synthetic histories, not evidence of real-world educational effectiveness.
- No RAGAS, DeepEval, TruLens, LLM, embedding model, or external service is used.

## Reproduction

```powershell
uv run --python 3.13 pytest
uv run --python 3.13 python -m evaluation.runner
```
