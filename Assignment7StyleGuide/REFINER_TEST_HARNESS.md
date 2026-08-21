# Refiner Test Harness

This harness validates the Assignment 7 Style Refiner before the full Generator → Evaluator → Refiner loop is assembled.

For each smoke-test case it runs a real automated cycle:

1. Send intentionally bad player-facing copy to the already-validated Style Evaluator.
2. Confirm the candidate scores below the acceptance threshold and that the expected style problem is detected.
3. Send the candidate plus the evaluator's SCORE, REASON, and rule violations to the Style Refiner.
4. Validate the Refiner's structured output locally.
5. Confirm the Refiner reports addressing every evaluator rule ID and does not invent new rule IDs.
6. Enforce the supplied word limit.
7. Send the revised player-facing copy back through the same Style Evaluator.
8. Require the score to improve, reach the acceptance target, and contain no remaining major violations.

The suite includes three different problems:

- tone + permanent-safety framing;
- invented lore + renamed ability;
- formatting / excessive length.

Default acceptance target: **9/10**.

Results are saved to:

`Assignment7StyleGuide/outputs/tests/refiner_test_results.json`

Run from the repository root:

`docker compose run --rm claude python3 Assignment7StyleGuide/test_refiner.py`

Run one case only:

`docker compose run --rm claude python3 Assignment7StyleGuide/test_refiner.py --case invented_lore_violation`

You can override the acceptance target for diagnosis:

`docker compose run --rm claude python3 Assignment7StyleGuide/test_refiner.py --acceptance-score 10`

The default test uses 9/10 because the purpose is to verify that the Refiner makes a materially successful automated correction without making the smoke test brittle over harmless evaluator scoring variation. The final production pipeline may choose a different configured threshold.

## Test-failure lesson

The first end-to-end refiner smoke run exposed an important integration requirement: the post-refinement Style Evaluator must receive the same `content_requirements` / task context as the Refiner. Otherwise it can falsely classify a canon-supported limitation as invented. The harness now preserves those task constraints through both the initial and final evaluation passes.

The default Claude turn budget is also 6 rather than 4 because valid evaluator calls were observed occasionally requiring 5 turns.
