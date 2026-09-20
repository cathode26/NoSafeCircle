# Keeping Windows quiet: no console pop-ups

Written 2026-09-17. Vincent, while working on his day job: "one of the agents is spamming command prompt / powershell. Can you tell them to do that invisible."

**The rule:** nothing an agent runs may open a visible console window on Vincent's desktop. A flashing window every few seconds makes the machine unusable for him.

---

## 1. Where pop-ups actually come from

Commands you type into the Bash or PowerShell tool run inside your session and show no window. A window appears when **a script you run spawns another process** without saying "no window".

| Cause | Fix |
|---|---|
| Python `subprocess.run` / `Popen` calling `git`, `powershell`, `docker`, `netstat`, anything | `creationflags=0x08000000` (`CREATE_NO_WINDOW`) on **every** call |
| PowerShell `Start-Process` | `-WindowStyle Hidden`, or `-NoNewWindow` when you want the output inline |
| `start`, `cmd /c start`, `explorer`, `wt` | Don't use them at all |
| A long job you want to keep running | The Bash tool's `run_in_background`, not a detached process |
| Unity | `-batchmode -quit -nographics`, launched through `unity-runner` or `run_unity_tests_clean.ps1`, which already hide it |

**Never** use `DETACHED_PROCESS` (`0x00000008`) or `CREATE_NEW_CONSOLE` (`0x00000010`). **`DETACHED_PROCESS` creates a console rather than suppressing one**, which is the opposite of what it sounds like. For a background child, use `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`.

### What actually caused it

Vincent reported console windows "spamming" while he worked. Three sources, all now fixed:

1. **A tool's background mode used `DETACHED_PROCESS`,** and its test suite exercised that path, so every test run flashed windows. This was the repeating one.
2. **Branch-triage and cleanup scripts called `git` through `subprocess.run` with no flag,** hundreds of calls per run.
3. **One-off contract patch scripts** did the same, a few flashes per run.

### A host `claude -p` job pops consoles, and you can't stop it

Measured on 2026-09-17 by counting `conhost.exe` (one per console) during a short job:

| Job | Consoles created |
|---|---|
| Host job using Bash, launched with `CREATE_NO_WINDOW` | +4 |
| Host job using only Read, Grep and Glob, same launch | +3 |
| Same file-only job launched with `Start-Process -WindowStyle Hidden` and redirected streams | +4 |

It's the CLI's own child processes, not the tools the job uses, so neither `CREATE_NO_WINDOW` on the launch nor a hidden window prevents it.

**What to do:**
- **Prefer Docker jobs.** Their processes live in the container and create no Windows consoles. This is also Vincent's rule: "the pipeline should go through docker and through cathode26@gmail.com".
- **Use a host job only when it needs the host:** files outside a repo clone, Windows-only tools, the PixelLab MCP, or a custom agent with `--agent`.
- **Batch them,** and avoid running several at once or while Vincent is working. Each job is a handful of flashes.

**The lesson: loops and test suites multiply a single missing flag.** A hand-run script flashes a few times; a poller, watcher or test that exercises a spawn path floods the desktop. If you own anything that spawns on a timer or in a loop, check it first.

---

## 2. Python, the common case

```python
import subprocess

NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW

result = subprocess.run(
    ["git", "-C", repo, "status", "--porcelain"],
    capture_output=True, text=True, creationflags=NO_WINDOW,
)
```

- Put `NO_WINDOW` at the top of every script that spawns anything, and pass it on **every** call, including the ones you think are quick.
- `capture_output=True` alone does **not** hide the window.
- For a long child process, keep `creationflags=NO_WINDOW` and poll it; don't detach it.

## 3. PowerShell

```powershell
Start-Process -FilePath python -ArgumentList '-B','script.py' -WindowStyle Hidden
Start-Process -FilePath python -ArgumentList '-B','script.py' -NoNewWindow -Wait
```

- `-WindowStyle Hidden` for fire-and-forget, `-NoNewWindow` when you want the output in your session.
- A bare `Start-Process` opens a window. There is no case in this project where that's wanted.

## 4. Check your own work

1. Run the command once and watch the taskbar. If anything flashes, the spawn is missing its flag.
2. Grep your script before you hand it over: `grep -n "subprocess\.\|Start-Process" <script>` and check every hit.
3. **Check for indirection before you report someone else's file.** A script can set the flag once and spread it, for example `FLAGS = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}` passed as `**FLAGS` to every spawn. Grepping for the literal `creationflags=0x08000000` misses that spelling, and it once produced a false report against three clean scripts. Grep for `creationflags` and `CREATE_NO_WINDOW` both, then read the spawn lines.
3. Scripts that Vincent runs himself (for example the Cleanup Agent's) follow the same rule, since they run on his desktop.

---

## 5. Where this rule already appears

The roster's checkpoint rules, the Pipeline Maintainer guide, the Release Agent guide, the viewer guide, the art bible, and the `pipeline-maintainer` and `pipeline-reviewer` agent files. This guide is the one to point at.
