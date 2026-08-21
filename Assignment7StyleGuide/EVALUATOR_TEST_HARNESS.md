# Evaluator Test Harness

This smoke-test harness validates the Assignment 7 Style Evaluator before the Refiner is wired into the loop.

It runs three deliberately different cases:

1. Known-good No Safe Circle player-facing copy.
2. Heroic tone + permanent-safety violation.
3. Invented lore + renamed ability violation.

The harness checks two things:

- **Structured output contract:** `content_id`, integer `score` from 1–10, non-empty `reason`, valid `violations`, valid No Safe Circle rule IDs, and the rule that score 10 has no violations while scores below 10 have at least one.
- **Behavioral expectations:** good copy should score high; deliberately bad copy should score low and identify an appropriate style-rule family.

Results are saved to:

`Assignment7StyleGuide/outputs/tests/evaluator_test_results.json`

Run from the repository root:

`docker compose run --rm claude python3 Assignment7StyleGuide/test_evaluator.py`

Run one case only:

`docker compose run --rm claude python3 Assignment7StyleGuide/test_evaluator.py --case tone_and_safety_violation`

The score bands are intentionally tolerant because LLM scoring can vary slightly between runs. The important requirement is that the evaluator recognizes the correct type of problem and returns valid machine-readable feedback.
