"""Replace the wrong autocrlf advice in the hash-gate memory with what was measured."""
import io

path = r'C:\Users\VincentLiguori\.claude\projects\C--NSC\memory\contract-hash-gates-use-committed-lf-blob.md'
data = io.open(path, encoding='utf-8').read()

old_start = "**Applying a patch to a pinned file: `git -c core.autocrlf=false apply`.**"
index = data.find(old_start)
if index == -1:
    print('anchor not found')
    raise SystemExit(1)

new_tail = """**Applying a patch to a pinned file: use the clone's own config. Do NOT pass `-c core.autocrlf=false`.**

The Game Agent advised that flag on 2026-09-17 and the Documentation Agent measured it failing: in a normal clone the worktree is CRLF and the patch is LF, so with conversion disabled git finds no matching context and **refuses the apply**. Applying with the clone's ordinary config worked, and the committed blob still came out LF and hashed to the pin - because the index normalises on commit, which is the part that matters.

Worse, the failure is asymmetric and easy to misread: **`git apply --check` passes under normal config, and then the `-c core.autocrlf=false` apply fails.** A check that passed does not predict the flagged apply succeeding.

Why the flag looked right: it was "verified" in a throwaway scratch repo whose file had been written from `git cat-file` output, so both sides were already LF and the flag changed nothing. A scratch repo is not a clone, and an experiment that cannot fail proves nothing - the same trap as a test fixture with no tests in it.

**The durable rule is the hashing one, not the applying one:** hash `git show <commit>:<path> | sha256sum`, never the file on disk. If the landed hash differs from the pin, report it and let the owner rebind - never edit approved prose to chase a precomputed hash.
"""

io.open(path, 'w', encoding='utf-8').write(data[:index] + new_tail)
print('memory corrected: the autocrlf flag advice is now marked wrong, with the measurement')
