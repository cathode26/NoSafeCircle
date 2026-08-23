# Stage 4 Provider-Adapter Capability Mapping

## Purpose and evidence basis

This document records behavior observed through opt-in live CLI probes that were isolated from production writes, plus the later bounded adopt-versus-build transport spike. It does not infer capabilities from generic provider knowledge. Unobserved behavior remains unsupported or unresolved until fixtures and evidence establish it.

Both `ClaudeCodeProvider` and `OpenAICodexProvider` are generic AgentRuntime providers with active read-only ArchitectureReview integrations. Stage 5A adds provider write mechanics for the exact `repository_read + repository_search + repository_write` combination only under the explicit, mutually distinct `externally_isolated_writable_repository=True` profile. The configured root must exist, be a directory, and resolve outside the real source checkout, neither equal to it, below it, nor an ancestor containing it. Claude exposes Read/Glob/Grep/Edit/Write while continuing to deny Bash and unrelated tools; Codex permits its provider-local inspection/edit mechanisms but receives explicit prohibitions on tests, builds, project scripts, and destructive Git operations. Both reject `approved_command_execution` and non-null `token_limit`.

`WriteBoundaries` are exact semantic prompt policy, with denied paths overriding allowed paths; neither adapter claims native path-level enforcement. The disposable workspace remains untrusted until a future higher-level deterministic Git diff check approves it. AgentRuntime and provider claims do not establish changed paths, test success, delivery, conformance, readiness, dispatch, integration, or commit/merge authority. ArchitectureReview continues to use only its existing read-only profiles.

## Tested versions and commands

### Claude Code

Tested version: `2.1.222`.

The non-interactive entry point was `claude -p`. The successful invocation received the prompt through stdin and used:

```text
claude -p \
  --safe-mode \
  --model sonnet \
  --effort low \
  --tools Read \
  --allowedTools Read \
  --disallowedTools Bash,Edit,Write \
  --permission-mode dontAsk \
  --input-format text \
  --output-format json \
  --json-schema <inline JSON> \
  --no-session-persistence \
  --max-turns 1
```

The successful discovery probe used a mounted Bash script and quoted shell expansion to pass the schema contents as one argv argument. That probe mechanism is evidence about the tested CLI interface, not the production invocation design: production adapter code must invoke the CLI directly without a shell and pass compact schema JSON as one subprocess argv element. The process exited `0` with empty stderr. Its result envelope included `type=result`, `is_error=false`, `subtype=success`, `terminal_reason=completed`, `stop_reason=tool_use`, `session_id`, `num_turns=2`, `duration_ms`, `duration_api_ms`, `total_cost_usd`, `usage`, `modelUsage`, `permission_denials`, `result`, and `structured_output`. The accepted candidate was:

```json
{"provider":"claude","message":"stage4-probe"}
```

The configured `sonnet` alias resolved to primary model `claude-sonnet-5`; `modelUsage` also reported auxiliary `claude-haiku-4-5-20251001` activity. This probe establishes discovery evidence only: production configuration must not use that alias. The CLI accepted `--max-turns` despite that option not being displayed in the observed help. The same invocation passed `--max-turns 1` while the result reported `num_turns=2`, so Claude's reported turn accounting must not be interpreted as a cross-provider-comparable unit.

### OpenAI/Codex

Tested version: `codex-cli 0.149.0`.

The non-interactive entry point was `codex exec`. The successful invocation received the prompt through stdin via the final `-` argument and used:

```text
codex exec \
  --ephemeral \
  --ignore-user-config \
  --ignore-rules \
  --strict-config \
  --skip-git-repo-check \
  --sandbox danger-full-access \
  -m gpt-5.6-sol \
  --output-schema <file> \
  --json \
  -o <final-output-file> \
  -
```

The probe ran in an empty mounted probe workspace under the externally read-only `codex-review` Docker service. It exited `0`. The final-output file contained:

```json
{"provider":"codex","message":"stage4-probe"}
```

The JSONL transcript contained `thread.started` with `thread_id`, `turn.started`, `item.completed` with an `agent_message`, and `turn.completed` with `usage`.

## Shared adapter responsibilities

Both adapters must:

- consume the exact `AgentRequest`;
- receive the concrete model selected by `RuntimeConfiguration`;
- return the exact `ProviderInvocationResponse`;
- deliver prompts through stdin;
- execute without persistent sessions;
- preserve a machine-readable raw provider transcript;
- expose only provider/agent claims;
- never establish delivery, conformance, readiness, authorization, approval, Git integration, or Unity success.

## Structured-output mapping

### Claude Code

- Serialize the compact schema JSON and pass it directly as one subprocess argv element, never through shell interpolation.
- Use `--output-format json` and parse exactly one result envelope.
- Use `structured_output` as the structured-output candidate accepted from the adapter.
- Preserve the complete result envelope as the raw provider log.
- Require `type=result`, `is_error=false`, `subtype=success`, `terminal_reason=completed`, and a present `structured_output`.
- Do not classify `stop_reason=tool_use` as failure. That value occurred on the successful schema-constrained probe.

### OpenAI/Codex

- Write the schema to a unique temporary file outside the repository and pass it with `--output-schema`.
- Use `--json` to obtain machine-readable JSONL raw events.
- Use `-o` to write the final structured-output candidate.
- Preserve the JSONL stream as the raw provider log.
- Require process exit code zero, existence of the final-output file, parseable final JSON, and a valid completed-turn event.
- Return the candidate to `AgentRunner`; central schema validation remains the runner's responsibility.

## Model mapping

- Approved production configuration must contain explicit concrete provider model identifiers. Aliases and automatic fallback are prohibited in production mappings.
- `AgentResult.model` is the model selected from configuration, including when a provider transcript reports a resolved or auxiliary model.
- Observed auxiliary or multi-model behavior must remain visible in the raw provider log.
- An adapter must not silently replace the configured model.

## Usage mapping

Normalized usage is provider-local audit data. Claude and Codex cache and reasoning categories have not been reconciled, so normalized token totals must not yet be treated as directly comparable measurements of provider efficiency, quality, or cost.

### Claude Code

- Prefer `modelUsage` when present so auxiliary-model activity is not discarded.
- Normalized `input_tokens` is the sum, across every model entry, of `inputTokens`, `cacheReadInputTokens`, and `cacheCreationInputTokens`.
- Normalized `output_tokens` is the sum of every model entry's `outputTokens`.
- `total_tokens` is normalized input plus normalized output.
- `estimated_cost_usd` may use `total_cost_usd`.
- If `modelUsage` is absent, map the top-level `usage` fields conservatively and document that fallback in adapter documentation and fixtures.

### OpenAI/Codex

- Use the last valid `turn.completed` usage event.
- Normalized `input_tokens` uses reported `input_tokens`.
- Normalized `output_tokens` is reported `output_tokens` plus `reasoning_output_tokens`.
- `total_tokens` is normalized input plus normalized output.
- Preserve `cached_input_tokens` and `cache_write_input_tokens` in the raw log; whether they are subsets or additive has not been independently proven.
- Set `estimated_cost_usd` to null because the observed JSONL contained no cost.
- The observed JSONL contained no model field, so the configured model remains the normalized result model.

## Capability support matrix

| `allowed_capabilities` | Claude Code initial mapping | OpenAI/Codex initial mapping |
| --- | --- | --- |
| empty set | Supported for structured-output-only work | Supported in an empty contained workspace |
| `repository_read` | `Read` | Supported with explicit externally read-only profile |
| `repository_search` | `Glob`, `Grep` | Supported with explicit externally read-only profile |
| `repository_read` + `repository_search` | `Read`, `Glob`, `Grep` | Supported with explicit externally read-only profile |
| `repository_write` | Unsupported; fail closed | Unsupported; fail closed |
| `approved_command_execution` | Unsupported; fail closed | Unsupported; fail closed |

The Claude live success probe was structured-output-only. Its read/search mappings come from the tested CLI tool interface and still require adapter fixtures before support is implemented. For both adapters, an empty capability set requires empty `context_paths`.

Initial Codex support is the empty capability set only. Each invocation must use a newly created empty temporary working directory; no repository working directory or repository context is supplied. Live use remains opt-in and non-production-write. `repository_read` and `repository_search` remain unsupported until a separately approved containment decision proves the required filesystem, command, credential, and network restrictions.

For supported Claude read/search combinations, `context_paths` remain task-context hints rather than a read-security allowlist. `write_boundaries` cannot currently be claimed as natively enforced by either observed CLI. Adapters may reject unsupported combinations and may never silently weaken requested restrictions.

## Budget mapping

`AgentRequest` remains schema 1.0 and retains its required positive integer `turn_limit`. Stage 4 does not require a request-schema bump.

The field is treated as a provider-neutral bounded-execution budget knob. Provider adapters may enforce that budget using different reviewed mechanisms, but the same numeric value must not be presented as an equal amount of model work across providers.

### Claude Code

- Pass `turn_limit=N` as native `--max-turns N`.
- Independently enforce `timeout_seconds` as the hard external subprocess ceiling.
- Therefore Claude is bounded by both the native turn flag and the external wall-clock deadline.
- The discovery run passed `--max-turns 1` and reported `num_turns=2`. That observed accounting mismatch does not disable the native flag, but it means provider-reported turn counts are not accepted as a provider-neutral metric.

### OpenAI/Codex

- Codex exposes no observed native turn-limit option.
- Use the approved temporary policy constant `OPENAI_SECONDS_PER_TURN = 30`.
- Compute `translated_turn_timeout_seconds = turn_limit * OPENAI_SECONDS_PER_TURN`.
- Compute `effective_timeout_seconds = min(timeout_seconds, translated_turn_timeout_seconds)`.
- The effective timeout is the hard external subprocess deadline for that Codex invocation.
- This is conservative wall-clock emulation of the request's bounded-execution budget. It is not a claim that 30 seconds is literally one Codex model turn.

Examples:

```text
turn_limit=1,  timeout_seconds=300 -> Codex effective timeout 30s
turn_limit=4,  timeout_seconds=300 -> Codex effective timeout 120s
turn_limit=20, timeout_seconds=300 -> Codex effective timeout 300s
```

Shared budget rules:

- Neither observed CLI natively enforces the provider-neutral `token_limit`; any non-null `token_limit` must fail closed.
- `ExecutionCrew` invocation/attempt limits and GER repair limits are separate later orchestration policy. They bound repeated invocations/repairs and do not redefine the per-invocation `turn_limit` mapping.
- Do not use Claude's `--max-budget-usd`; `AgentRequest` currently defines no provider-neutral dollar budget.
- Do not compare providers using `turn_limit` as if it measured equal reasoning steps, model calls, quality, cost, or latency.

## Isolation and ambient configuration

### Claude Code

- Use safe mode and no session persistence.
- Supply an explicit tool set and `dontAsk` permission mode.
- Configure no fallback model.
- Do not rely on project or custom instructions.

### OpenAI/Codex

- Use ephemeral execution, ignore user configuration and rules, and require strict configuration.
- Disable web search.
- Create a new empty temporary working directory for every invocation and supply no repository context.
- Do not claim read/search support unless a separately approved containment decision proves filesystem, command, credential, and network restrictions.

## Raw logs and errors

Preserve exact machine-readable provider stdout as `provider.log`. A successful exit requires empty stderr. Exit code zero with non-empty stderr is `internal_error` until a fixture proves that exact stderr is benign. For a nonzero exit, preserve stdout unchanged as the raw log and use safely decoded stderr for the normalized provider diagnostic. Stderr must never be appended to or otherwise alter `provider.log`.

Docker lifecycle stderr is not itself a provider failure when the eventual adapter is invoked directly inside the runtime container. Adapter failure classification must be conservative:

- `provider_error`: a recognized provider failure envelope or nonzero provider exit not more specifically classified;
- `timeout`: the externally enforced subprocess deadline expired;
- `permission_denied`: an observed, unambiguous provider permission denial;
- `budget_exhausted`: an observed, unambiguous provider budget-exhaustion condition;
- `schema_error`: a provider-neutral `ProviderOutputInvalid` exception (or equivalent name) reports output that cannot produce a structured-output candidate, or central `AgentRunner` schema validation rejects a successfully parsed candidate;
- `internal_error`: adapter/process setup, temporary-file, transcript-processing, unexpected successful stderr, or other unexpected local failure.

Stage 4 implementation must add `ProviderOutputInvalid`, or an equivalently named provider-neutral exception, to `providers/base.py` and map it to `schema_error`. It covers malformed or missing Claude result envelopes or `structured_output`; malformed or missing Codex final output; a missing valid Codex completed-turn event; and any provider output that cannot produce a structured-output candidate. `AgentRunner` remains responsible for validating a successfully parsed candidate against `AgentRequest.output_schema`.

## Stage 4C implemented Codex mapping

`OpenAICodexProvider` now supports `()`, `repository_read`, `repository_search`, and their combination. Repository-capable calls require an explicit externally enforced read-only provider profile; ArchitectureReview supplies it because `codex-review` mounts the repository read-only. Empty calls use a fresh temporary workspace outside the repository. Repository write, approved command execution, non-null token limits, and fallback fail closed.

Codex receives the concrete model selected by RuntimeConfiguration, a validated provider reasoning effort, schema/final-output temporary files, stdin prompt, and JSONL output mode. The shared process runner enforces `min(timeout_seconds, turn_limit * 30)`. Exact JSONL stdout is the provider log; the last valid completed-turn event supplies usage, with reasoning output added to normalized output tokens. AgentRunner remains final schema authority.

Provider-specific failure envelopes have not yet been observed. Fixtures covering them are required before production use; ambiguous failures must not be guessed into a more specific classification.

## Provider-transport adopt-versus-build spike

Before implementing the live adapters, two public projects were evaluated to determine whether Stage 4 could reuse a finished shared transport layer.

### `agent-mux`

Result: not adopted.

Observed positives:

- one dispatch contract across Claude Code and Codex;
- process supervision, timeout handling, event parsing, token/activity normalization, and persistent dispatch artifacts;
- existing CLI/OAuth authentication can be reused.

Observed mismatches:

- the tested source commit `4a27d544f8beeee172d9a509d917342a27ca9d7a` failed its documented Linux source build because `internal/supervisor/reaper_linux.go` referenced unavailable `syscall.Prctl`;
- a disposable local patch from `syscall` to `golang.org/x/sys/unix` was required before the probe binary would build;
- its Claude invocation contract does not match the exact safe-mode, no-session-persistence, explicit tool-control, and `--json-schema` path established by our discovery probe;
- its Codex invocation contract does not match our required `--ephemeral`, ignored-user-config/rules, strict-config, output-schema/final-output-file, and empty-workspace boundary;
- adapting or forking those behaviors would make us maintain a larger external transport abstraction while still owning the policy-critical differences.

The patched disposable binary successfully executed `--version`, and the No Safe Circle repository remained clean. The spike did not add `agent-mux` to the project.

### `agent-shell`

Result: not adopted.

Observed positives:

- Python implementation;
- reusable process-group cleanup, concurrent stdout/stderr draining, streaming parsing, model discovery, and provider adapter patterns.

Observed mismatches:

- unsupported Claude/Codex allowed/denied tool restrictions can produce warnings and continue rather than fail closed;
- its Codex adapter cannot enforce the project capability contract and intentionally ignores some requested tool restrictions;
- its default approval/sandbox and prompt-delivery mechanics do not match the approved Stage 4 containment contract;
- adopting it would require wrapping or replacing its policy semantics, reducing the benefit of the dependency.

The project may borrow implementation patterns from both libraries, but neither is a production dependency or authority. The narrow Claude Code and OpenAI/Codex providers will be implemented directly under `Pipeline/AgentRuntime/providers/`.

## Initial Stage 4 implementation boundary

- Keep `AgentRequest` schema 1.0 and the existing required integer `turn_limit`.
- First implement provider-neutral `ProviderOutputInvalid` and map it to `schema_error`; this is the only remaining AgentRuntime prerequisite before live provider adapters.
- The first Claude adapter may support structured-output-only and the explicitly mapped read/search combinations after fixtures prove them.
- The first Codex adapter supports structured-output-only with an empty capability set in a newly created empty temporary directory.
- Apply the reviewed provider-specific `turn_limit` enforcement mapping described above.
- A non-null `token_limit` fails closed.
- No production repository writes are permitted.
- Approved command execution is unsupported.
- Automatic provider fallback is unsupported.
- `ExecutionCrew` role orchestration is out of scope.
- No real gameplay task will be executed.
- Live smoke tests are opt-in only and must perform no production writes.

## Open issues

- fixtures proving the Claude `--max-turns` invocation mapping and the Codex 30-seconds-per-unit timeout translation;
- approved external containment for Codex repository read/search;
- path-level write enforcement;
- command allowlisting;
- fixtures for provider-specific failure envelopes;
- explicit model selection for every capability class;
- later evidence on whether the temporary `OPENAI_SECONDS_PER_TURN = 30` policy should be tuned, replaced, or removed.

The accepted immediate prerequisite is implementation and review of provider-neutral `ProviderOutputInvalid` normalization. A request-schema bump is no longer part of the Stage 4 prerequisite.
