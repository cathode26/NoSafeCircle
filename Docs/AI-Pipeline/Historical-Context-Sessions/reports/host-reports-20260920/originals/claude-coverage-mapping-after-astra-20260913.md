Implement the bounded coverage-mapping author guidance fix in this checkout only.
Read C:\nscrev\reports\codex-prompt-coverage-mapping-fix.md, AGENTS.md, the applicable testing guidance, and current code. Your branch is codex/coverage-mapping-guidance-20260913 at exact base 4fd54b8ce167bd87897926384839b03378e86232. Do not write under C:\NSC, push, merge, invoke another provider, or run Docker.

Astra reviewed the exact base read-only and gave GO with these requirements:
- Preserve policy.py's parent AC/VAL same-kind target rule and full (child local_key, collection, entry ID) ownership. Parent INT neither claims nor conflicts with restricted ownership; a parent can target several children. Explain integration-flavoured parent VAL is not exempt.
- Aggregate only the specified target defects and missing parent coverage within policy.py's mapping block, then raise before later checks. Guard unknown-child lookups; stable first owner; record/target order and sorted missing IDs. Preserve early structural, unknown/duplicate parent, disposition checks and later untraced-child checks. Do not blanket replace all raises.
- Put the shared coverage guidance in the author prompt, correction (which embeds author), and reviewer prompt. The reviewer presently shares only the evidence block.
- Keep aggregate within one exception and one rejection-list element. Existing full rejection delivery to correction is already correct; do not change the orchestration or the three-call design.
- Preserve exact existing single-error text. Tests must include guidance in all three prompts, combined defects in deterministic order, parent INT sharing in both orders, early-error preservation, invalid reviewer revision, and a stubbed correction showing the full aggregate reaches request/prompt within call cap. New tests should fail before implementation; run the suites specified in the report.

Make the change and tests in this branch, commit using non-attributable .invalid Git identity. Report commit SHA, test counts, and residual risks. Do not change unrelated game files.
