# Windows Task-Clone Correction

This note is an authoritative Windows-specific correction to Section 2 of `REAL_TASK_DELIVERY_RUNBOOK.md`.

## Rule

On this development machine, create standalone task clones from the GitHub remote, **not** by cloning the local `NoSafeCircle` checkout.

Do this:

```powershell
cd C:\UnityProjects\NoSafeCircleAgentCrew
git clone https://github.com/cathode26/NoSafeCircle.git NoSafeCircle-NSC###
cd .\NoSafeCircle-NSC###
git switch -c nsc-###-short-description
```

Do not use this local-source form on this machine:

```powershell
git clone .\NoSafeCircle .\NoSafeCircle-NSC###
```

Git for Windows has rejected that local-source clone with `detected dubious ownership` because the source `.git` directory is owned by `BUILTIN/Administrators` while the interactive user is `VincentLiguori`.

Do not work around this by broadly adding the local source repository to global `safe.directory` merely to create task clones. Cloning from GitHub avoids the ownership ambiguity and gives the standalone task checkout a normal `.git` directory suitable for the Docker ExecutionCrew workflow.

## Docker Compose project name is fixed for task clones

A standalone task clone has a different directory name such as `NoSafeCircle-NSC019`. Docker Compose normally derives its project name from that directory. If ExecutionCrew is launched with plain `docker compose run ...`, Compose can therefore create clone-specific resources such as:

```text
nosafecircle-nsc019_claude-config
```

instead of reusing the already configured/authenticated provider volume owned by the normal project:

```text
nosafecircle_claude-config
```

That can make the provider fail immediately before modifying any files, even though the task contract and repository preflight are valid.

Therefore, when running ExecutionCrew from any standalone task clone on this development machine, **always pin the Compose project name explicitly**:

```powershell
docker compose -p nosafecircle run --rm -T claude-exec python3 Pipeline/ExecutionCrew/run_crew.py `
  --task-id NSC-### `
  --provider claude `
  --implementation-path <tracked-production-path> `
  --test-path <tracked-test-path> `
  --host-output-root "C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle-NSC###\Pipeline\ExecutionCrew\outputs"
```

The two operational parameters that must not be accidentally omitted are:

- `-p nosafecircle` — forces every standalone clone to reuse the normal Compose project namespace and its existing provider-config/auth volumes instead of creating `nosafecircle-nsc###_*` volumes;
- `--host-output-root "C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle-NSC###\Pipeline\ExecutionCrew\outputs"` — tells ExecutionCrew the Windows host path corresponding to its mounted output root so `crew_result.json` and the human footer contain copy/paste-ready host paths to `candidate.patch` or diagnostic artifacts.

Keep `--rm -T` as shown as well: `--rm` removes the disposable run container after completion, and `-T` disables pseudo-TTY allocation for the machine-readable execution path.

Do not remove `-p nosafecircle` merely because the task checkout itself is isolated. The **Git checkout should be isolated; the provider authentication/config volume should be shared**.

## Verification after cloning

Run:

```powershell
git status --short
git log -1 --oneline
git remote -v
```

The working tree should be clean, the clone should be on the current remote `main` history, and `origin` should point at the GitHub repository.

This note overrides the clone-source command and fixes the Docker Compose project-name requirement for standalone task clones. The rest of the standalone-clone, feature-branch, ExecutionCrew, Unity-validation, evidence, conformance, and merge workflow remains unchanged.
