All three blockers fixed, tested, and hand-verified. Summary:

**Changes** (only `run_job.py`, `tests/test_run_job.py`, `tests/review_mutation_check.py` touched; backup at `run_job.before-round3.bak.py`):

1. **Packed `--allow-tool` rules** — added `split_tool_rule_value()`, which splits on commas/whitespace outside parentheses (so `Bash(git status:*)` survives intact). `resolve_job` now splits each `--allow-tool` value and validates every resulting rule independently before appending; `guard_tool_list` splits each entry the same way as its belt-and-braces pass.
2. **`Bash(*)` and friends** — added `_bash_specifier_is_unconstrained()`, refusing any Bash specifier that, stripped, is empty or made only of `*`, `:`, `.`. Name match was already case-insensitive via `.lower()`. `Bash(git log:*)`/`Bash(git status:*)` still pass.
3. **`guard_out` ancestor gap** — now refuses when `is_under(resolved, FORBIDDEN_ROOT) OR is_under(FORBIDDEN_ROOT, resolved)`, reusing the existing identity-based `is_under`, so `C:\`, `C:/Users/..`, `//localhost/C$`, `//?/C:/` are all caught in the ancestor direction too.

**Tests:** 101 → 112 (all green, 41s). Added packed-rule refusal + split-still-works cases and `guard_tool_list` direct tests to `ReviewAllowToolWidening`, plus a new `ReviewOutGuard` class (direct calls against the real `FORBIDDEN_ROOT` for the ancestor spellings, plus an end-to-end CLI case via the fixture). Had to adjust one pre-existing test (`test_a_malformed_rule_is_refused`): `"not a rule!"` is no longer malformed once whitespace-splitting is correct (it's 3 separate word-tokens, one of which parses as a syntactically valid but unknown tool name) — replaced with single-token malformed inputs (`"Bash(unterminated"`, `"not-a-rule!"`) that stay malformed after the fix.

**Mutations:** 16/16 caught (13 original + 3 new, one per blocker, each anchored on the guard function itself).

**Manual reproduction:** all of the reviewer's exact repro strings for all three blockers now refused by hand; legitimate neighbors (`Bash(git log:*)`, `--allow-bash git`, a normal `--out` under the sandbox) still work.

**Noted but out of scope** (not one of the three, didn't touch it): `--allow-bash .` would build `Bash(.:*)`, whose specifier is only `.`/`:`/`*` chars — the same unconstrained shape as blocker 2, but reached via `--allow-bash` rather than `--allow-tool`, and `--allow-bash`'s only validation today is "bare program name." Flagging for you to decide whether it's worth a follow-up problem entry rather than fixing it here.
