Warning: no stdin data received in 3s, proceeding without it. If piping from a slow command, redirect stdin explicitly: < /dev/null to skip, or wait longer.
```text
VERDICT: APPROVE
```

`d79bc26a9` does not bring back the round-1 defect. No real model id can contain a Cc or Cf character, so the new rule rejects nothing legitimate on the live pooled path.

**Can a real model id contain Cc or Cf? No.** Reproduced with a probe against the head code:
- Every printable ASCII character from 0x21 to 0x7E is accepted inside a value. Every Cc character and 165 of the 170 Cf characters in Python 3.13's Unicode 15.1 table are above U+007F, so an ASCII id cannot hit the rule.
- These id forms all pass:
  - the ids used in this repo: `claude-opus-5`, `claude-opus-5[1m]`, `claude-sonnet-5`, `gpt-5.6-sol`, `gpt-5-codex`, `gpt-6-astra`
  - a Bedrock id `us.anthropic.…-v1:0` and a full Bedrock ARN with `:` and `/`
  - the Vertex form `claude-opus-4@20250514`
  - an OpenAI fine-tune id `ft:…:org:suffix:id`
  - `vendor/model:tag`
  - an Azure-style deployment name
  - `--privileged`
- Provider ids are API and CLI tokens, and every provider this pipeline routes to issues them in printable ASCII.
- A future non-ASCII id still passes: `模型-5` and `modèle-5` are accepted, because letters and combining marks are not Cc or Cf.
- Variation selectors are category Mn, not Cf. U+FE0F is still accepted, so the rule is a little narrower than your brief assumed.
- A Cc or Cf character can plausibly arrive only by accident: a soft hyphen or zero-width character pasted from a web page, or a stray BOM. The provider would reject such a value as an unknown model after a container start. Refusing it earlier with the character visible in the `{value!r}` message is strictly better.
- Round-2 minor #2 is unchanged. These refusals still raise after the leases are reserved. This commit widens that refusal only to values that were already unusable, so it stays minor.

**Findings (most severe first):**
- [minor] Your brief names the wrong test: the three cases were added to `test_only_unusable_model_values_are_refused` (`test_decomposition_transport.py:171`), not `test_model_values_cannot_smuggle_an_argument` (`:205`). The commit itself is correct. Reproduced.
- [minor] `live_decomposition.py:266-268`: the C0 separators U+001C–U+001F and U+0085 are Cc, but they are reported as "contains whitespace" because the `isspace()` check runs first. They are still rejected; only the message differs. Reproduced.
- [minor] `live_decomposition.py:269-273`: the comment and the code now agree on Cc and Cf. The comment cites "a review" without naming a round or report. Still rejected, only the wording is loose.

**Tests re-run by reviewer** (`TEMP` and `TMP` set to `C:/nscrev/tmp/rev-delta`):

| Where | Suite | Result |
|---|---|---|
| Head `d79bc26a9`, author's clone | `test_decomposition_transport` | 19 OK |
| | `test_decomposition` | 40 OK |
| | `decomposition_session_pool_smoke_test.py` | 15 PASS |
| | `host_decomposition_launcher_smoke_test.py` | 20 PASS |
| | `mixed_provider_mutation_check.py` | 11 of 11 caught |
| New tests on `cf2ddc5f3`'s `live_decomposition.py`, my throwaway clone | `test_decomposition_transport` | 19 run, 3 failures |

- The three failures are exactly `a\x9bb`, `a\u200bb` and `\ufeffclaude-opus-5`, so the new cases fail before the change and pass after it.
- I piped the mutation check through `tail`, so I did not capture its exit code or the baseline line. I read only the "all 11 pieces of the fix are pinned by a test" result.
- `git diff --check` is clean. Both changed files have no BOM and are CRLF on every line (870 of 870 and 330 of 330), so there is no line-ending churn. The delta is +10/-1 across 2 files.
- Not run: Docker, Unity, providers, `taskcontrol validate`.

**Scope check:**
- **Intended files only:** yes, the two files in the delta.
- **New blocking gates:** none. The existing well-formedness check now also covers values that were never usable.
- **Temp under `C:\NSC`:** none. I wrote nothing there. My after-the-fact scan of `C:\NSC` for recently written files timed out, so I stopped it and that check did not complete.
- **Identity:** `No Safe Circle Pipeline Maintainer <pipeline-maintainer@nosafecircle.invalid>`, the same as the two approved commits. The round-2 note about the new role name still stands.
- **Windows:** no subprocess was added. `unicodedata` is in the standard library.
- **Author's clone:** clean at `d79bc26a9` on `fix/mixed-provider-model-env`, unchanged by me. I removed my throwaway clone `C:/nscrev/review-tmp/mpe-delta`.
