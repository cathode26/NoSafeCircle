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

## Verification after cloning

Run:

```powershell
git status --short
git log -1 --oneline
git remote -v
```

The working tree should be clean, the clone should be on the current remote `main` history, and `origin` should point at the GitHub repository.

This note overrides only the clone-source command in the current runbook. The rest of the standalone-clone, feature-branch, ExecutionCrew, Unity-validation, evidence, conformance, and merge workflow remains unchanged.
